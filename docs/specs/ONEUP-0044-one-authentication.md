# ONEUP-0044 — One authentication for a size preview and the run that follows

**Status:** Reviewed
**Kind:** fix
**Roadmap:** ONEUP-0044
**Branch:** v2
**Verified at:** `7d8d004` — every claim naming a symbol below was resolved against this
tree, not recalled. Every measurement names the command that produced it.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** One engine process spans the download-size preview and the run that
follows it, so the user authenticates once instead of twice — and never sees two password
boxes on screen at the same time.

## 1. Goal

A user who presses **Show download size** and then starts the update is asked to
authenticate **once**. Today they are asked twice, and because the two requests come from
two separate operating-system processes the two password boxes can be on screen
simultaneously — which is what makes the behaviour read as a fault rather than as a second
question.

After this ships, one engine process spans both jobs: it authenticates, reports the size,
waits a bounded time for the window to say *go* or *cancel*, and — on *go* — performs the
run itself, still holding the credential it already obtained.

## 2. Background

### 2.1 There are two engine processes, not one

The roadmap bullet's premise — "one engine invocation" — is wrong, and that is why every
attempt to reproduce the fault against a single invocation raised no dialog at all.

`oneup/gui/run.py`'s `request_size` starts the engine for the download-size query on its own
`_size_proc`, and the same file's `_launch` starts a second engine on `proc` for the run.
Both are `bash <engine> …` launches through `QProcess`.

> Measured: `grep -c '.start("bash"' oneup/gui/run.py` → `2`.

`--size=<step>` dispatches to `update_system.sh`'s `run_size`, which calls `sudo_init`
before its dry run. The run reaches `sudo_init` too, from the main dispatch. `sudo_init`
runs `sudo -A -p "System Updater: authenticate to update the system" -v`.

> Measured: `grep -cE '(^|[[:space:]]|&&[[:space:]])sudo_init[[:space:]]*$' update_system.sh`
> → `5` — the call sites in `run_size`, `grant_auth`, `revoke_auth`, `thin_snapshots` and
> the main dispatch. The trailing anchor excludes the function definition.

### 2.2 Why two processes means two dialogs

With no terminal — the window runs the engine through `QProcess` — sudo keys its cached
credential to the **parent process id**, per `sudoers(5)`'s `timestamp_type`, whose `tty`
default falls back to the ppid when no terminal is present. The engine records this in the
comment above `sudo_capture`, and it is the mechanism ONEUP-0038 was fixed against.

The two engines are different processes, so they hold different timestamp records, so each
authenticates on its own account. This is true whether or not they overlap: serialising the
two launches would remove the simultaneity without removing the second dialog.

**Simultaneity is the part only two processes can produce.** `sudo -A` blocks until its
dialog is answered, so one process cannot have two boxes open at once however many times it
calls `sudo_init`. The reporter saw two sixteen seconds apart, both still waiting — a size
fetch, then a run started shortly after it.

**This is now reproduced.** `tests/run-tests.sh` carries the scenario "a size preview and a
run that overlap cost exactly one password prompt", which stages both engines so that one is
provably alive while the other authenticates, and counts authentications across both. It
fails on this tree, counting 2 where 1 is expected.

### 2.3 The window guards this in one direction only

`request_size` refuses to start a second preview while one is in flight ("a fetch is already
in flight"). `_launch` has no corresponding guard: starting a run while a preview is running
is entirely unguarded.

> Measured: `sed -n '139,160p' oneup/gui/run.py | grep -c _size_proc` → `0`.

### 2.4 The preview cannot simply drop the privilege

The obvious fix — make `run_size` skip `sudo_init` — does not work, because the dry run
itself requires root. Run unprivileged on the machine this was measured on (zypper 1.14.98):

> Measured: `env LC_ALL=C zypper --non-interactive dup --allow-vendor-change --dry-run` →
> exit `5`, `Root privileges are required to run this command.`

Exit 5 is the code `run_size`'s own error table already maps to *"OneUp wasn't allowed to
run the check as administrator"*. Dropping the privilege would turn the preview into a
permanent failure.

### 2.5 Who is affected

Nobody who has turned on **Remember my authorization** (ONEUP-0023). `sudo_init` returns
early through `auth_current` when the drop-in is live and grants what the engine needs, and
`auth_cmnds` already covers the preview's argv through its `env LC_ALL=C zypper *` entry.
The fault is confined to users without the drop-in — which is the default state, and the
state the report came from.

## 3. Scope decisions (agreed with the user)

1. **One engine process, held open.** Chosen by the user on 2026-08-22 from three options.
   The two rejected alternatives are in §9 with the reasons they lost; they were live
   choices, not straw men.
2. **The contract to satisfy is "exactly one authentication", not "never two at once".**
   That is what the reproduction scenario already asserts, and it is the stricter of the two
   readings of the report.
3. **A held engine may not commit to a transaction without an explicit go-ahead.** If the
   window is gone, the engine exits rather than proceeding. This is deliberately the
   *opposite* of ONEUP-0042's rule for a committed run, and §4.4 says why.

## 4. Design

### 4.1 What must not change: the marker contract is frozen

`docs/reference/marker-protocol.md` §5.1 freezes the marker contract for the duration of
2.0 — the Python engine (ONEUP-0054) must ship it byte-identical, and gate **G2** compares
v1's and v2's marker streams under identical mocks and requires them to be equal. §5.1
grants exactly one exception, ONEUP-0072, and says "Never both at once".

**So this design adds no marker and changes no marker's field layout.** An earlier framing
of this work assumed a new "waiting for your go-ahead" marker. That is forbidden until the
rewrite has passed its gate, and it turns out to be unnecessary.

The route the freeze does not cover is §8 of that same reference: `run.state` and
`stop.request` are a contract between the two halves that is **not part of the protocol**,
because the window *writes* them, "which nothing in §1 permits". A go-ahead is the same
shape as `stop.request` — a file the window creates to ask the engine for something — so it
lands in §8 rather than in §1–§5.

### 4.2 The held engine

The window passes a new flag alongside the existing size request:

```
bash update_system.sh --size=system --hold --log=<path>
```

`--hold` is ignored unless `--size` is present. With it, `run_size` behaves exactly as it
does today up to and including its `@@SIZE@@` marker, and then, instead of
returning into the dispatch's `exit $?`, enters the hold:

```
hold_for_go_ahead()                 # RECORDS a decision; it never runs a step itself
  write   $HOLD_STATE_FILE          # see §4.3 for the pinned layout
  poll    every $STOP_POLL_SECONDS, up to $ONEUP_HOLD_SECONDS:
            go.request   newer than hold.state -> adopt its steps (below), return 0
            stop.request newer than hold.state -> return 1
            kill -0 $WINDOW_PID fails (window gone) -> return 1
  ceiling reached                              -> return 1
  always: rm -f $HOLD_STATE_FILE
```

**`--hold` suppresses `run_size`'s `@@DONE@@`, and that is a stream-ordering decision the
freeze does not make for us.** Today `--size` ends the process, so its `@@DONE@@` is the
last line of a stream and the reference describes exactly one per run (§4.9). A held
engine that emitted it and then ran would put two in one stream, the first saying `ok`
before any step had run. The window's own run does not misread it — `handle_marker` only
records `_done_status`, and `on_finished` takes the verdict from the exit code — but
§4.9's exception is the case that breaks: for a run another window merely **followed**
through `run.state`, `DONE` is "the only verdict there is". So `@@DONE@@` is emitted once
per process, at the true end. This adds no marker and changes no field layout (§4.1),
because ordering is not field layout — but it does change what a `--size --hold` process
prints, so INV-5a's harvest must cover the held stream as well as an ordinary run's.

**The hold records; it does not run.** The run is not a function this could call — the
engine's step code is straight-line script *below* the `--size` dispatch, and the engine
already records why that matters in the comment above `system_txn_argv` — "that dispatch
calls run_size and then exits", so anything "further down the file has never been executed
and does not exist yet". So a go-ahead returns 0 and the
`--size` dispatch's `exit $?` becomes conditional on the hold's result, letting control
reach the existing run path.

**Setting `STEPS` is not enough, and this is the one place the fall-through can look right
and run the wrong thing.** The run path does not read `STEPS`. `step_selected` does, but
its callers ran long ago: `RUN_KEYS`, `TOTAL`, `STEP_INDEX` and the `TOTAL == 0` rejection
are all derived at script top level, far **above** the `--size` dispatch, and the run loop
iterates `"${RUN_KEYS[@]}"` while `run_step`'s header and `@@STEP_BEGIN@@` report `$TOTAL`.
A go-ahead that only assigned `STEPS` would fall through and run whatever was derived at
startup — and `request_size` passes no `--steps=`, so that is the **default all five**. The
user's `cache` selection would silently become a full system upgrade.

So adopting a go-ahead means re-deriving the selection, in this order: validate every key
against `LABEL` (§4.6), assign `STEPS`, rebuild `RUN_KEYS` by re-running the same
`for k in system flatpak firmware orphans cache` loop, reset `TOTAL` and `STEP_INDEX`, and
re-apply the `TOTAL == 0` rejection to the rebuilt list. INV-6 is what catches an
implementation that skips this.

**The held path must then SUPPRESS the main dispatch's `sudo_init`**, which is the one
line that makes this design work. Falling through reaches `$needs_sudo && sudo_init`, and
`sudo_init` has no re-entry guard — its only early return is `auth_current`, which is
false precisely for the users this fix is for. Re-entering it does two things, and the
second is worse than the first: it re-runs the interactive validate, and it spawns a
**second keep-alive**, overwriting `SUDO_KEEPALIVE` so `cleanup`'s group kill can only
reach the later one. That is the orphaned-keep-alive leak of ONEUP-0041 and
`docs/standards/security.md` §2.4, and this design is the first thing in the engine that
would make it reachable — every existing `sudo_init` call site sits in a dispatch block
that exits, so no process reaches two of them today. INV-9 pins it.

Suppression is a flag the hold sets, not a change to `sudo_init`'s five call sites.
`release_zypper_lock` sits immediately after and is re-entered harmlessly, so it is left
alone.

**How the engine learns the window is gone: it captures `WINDOW_PID=$PPID` at startup and
then polls `kill -0 "$WINDOW_PID"`.** Under `QProcess` the engine is a direct child of the
window, so `$PPID` at startup is the window; once that pid stops existing the window is
gone. This is the idiom `sudo_init`'s keep-alive already uses — `while kill -0 "$1"` — so
the engine has one way of asking this question rather than two.

**Do not watch `$PPID` for a change.** Bash sets `PPID` once at shell start and never
refreshes it on reparenting, so `$PPID != $WINDOW_PID` compares a constant against a copy
of itself and can never fire. Measured on this machine: a child whose parent exited kept
`$PPID=170203` for its whole life while its real parent moved to `1309`.

**Do not test `$PPID` against 1 either.** Under systemd a user session's orphans are
reparented to `systemd --user`, not to init, so a pid-1 test silently never fires. This
engine has already paid for that mistake once: `reap_orphaned_askpass` carries the
measurement — "an orphan-check against pid 1 silently never fires (measured — it was the
first version of this function and it reaped nothing)". The same run above measured the
reparent target as `1309`, not `1`. Both mistakes fail the same way: a check that reads as
a guard and never runs.

A `--hold` run started by hand from a shell captures that shell as `WINDOW_PID`, and the
shell outlives the hold, so `kill -0` keeps succeeding and only the ceiling ends it. That
is correct — there is no window to have gone away.

**On anything other than a go-ahead the engine exits and the window must clear its own
held-engine state.** It cannot rely on today's `_on_size_finished` to do it: that handler
opens `if not row or row.has_size(): return`, and a hold exists only after `@@SIZE@@` has
arrived, so `has_size()` is true and it returns without reading the exit code. §4.5 says
what the window does instead.

### 4.3 Two new state files, and one reused signal

Both live beside the existing two, in the directory the marker reference's §8 pins — the
engine's `ONEUP_STATE_DIR`, the window's `_state_home` — and both are overridable in the
engine only, matching the existing pair:

| File | Written by | Deleted by | Override |
|------|-----------|-----------|----------|
| `hold.state` | the engine, when the hold begins | the engine, on every exit from the hold | `ONEUP_HOLD_STATE` |
| `go.request` | the window, to say proceed | the engine, when it reads one or when the hold ends | `ONEUP_GO_FILE` |

**Both layouts are pinned line by line, because a contents list is not a layout.**
`run.state`'s equivalent is pinned that way in `docs/specs/ONEUP-0054-python-engine.md`
§4.1.1 — down to "Lines 1–3 therefore may not be reordered or dropped" — precisely so the
Python engine can reproduce it, and §10 claims the same reproducibility for these two.

```
hold.state                        go.request
  line 1  engine pid                line 1  comma-separated step keys
  line 2  log path, verbatim
  line 3  the quoted size
```

`hold.state` line 1 is the only line the window reads (§6, to tell a live hold from one a
killed engine left behind). `go.request` line 1 is the only line the engine reads. Extra
lines are ignored by both halves; a missing line 1 makes the file invalid and it is
treated as absent.

**Cancel needs no new file, but it does need its own comparison.** `stop.request` already
means "the user asked to stop" and both halves already agree on it, so the window's Cancel
writes that. **The hold may not call `stop_pending` to read it.** That function requires
`[[ -e "$RUN_STATE_FILE" && "$STOP_FILE" -nt "$RUN_STATE_FILE" ]]`, and a hold has
deliberately not written `run.state` — so `stop_pending` is false for the whole hold and a
Cancel button wired through it would do nothing for the full 120 seconds. The hold compares
`stop.request` against `hold.state`, which is its own stamp.

**`run.state`'s layout is untouched.** It is pinned in
`docs/specs/ONEUP-0054-python-engine.md` §4.1.1 and the Python engine must reproduce it
exactly, so a held engine writes `hold.state` and writes `run.state` only when it commits to
the run — unchanged from today. A hold is not a run.

**Staleness is decided the way `stop_pending` decides it**, and for the same reason: a
request older than the stamp is a leftover from an earlier session. `hold.state` is the
stamp, so a `go.request` counts only if it is newer than `hold.state`. Deleting leftovers at
startup instead would race a go-ahead pressed in that same moment, exactly as
`stop_pending`'s own comment records.

### 4.4 The hold is bounded, and the ceiling is not arbitrary

`ONEUP_HOLD_SECONDS`, default **120**.

Two independent reasons the hold must end by itself:

1. **The credential expires.** This machine's sudoers sets `Defaults targetpw` and no
   `timestamp_timeout`, so sudo's compile-time default applies. A hold longer than that
   window would reach its go-ahead with a cold credential and prompt again — reintroducing
   the second dialog by the back door. The ceiling must stay comfortably under it.
2. **A held engine is unattended privilege.** ONEUP-0042 requires a *committed* run to
   survive the window going away, because abandoning a transaction mid-flight is worse than
   finishing it. A held engine has committed to nothing, so the opposite applies: with no
   window there is nobody to authorise anything, and it must exit.

**Expiry is not a failure, and the two statuses here are different things.** Inside the
engine `hold_for_go_ahead` returns **non-zero** on expiry, on Cancel and on a departed
window — that is how the caller knows not to fall through into the run. The `--size`
dispatch then maps all three to **exit 0**, because the job the process was started for —
quoting the size — succeeded and was already reported. Without that mapping a user running
`--size --hold` in a terminal sees a failure for a run they simply chose not to start.

So the window re-arms the link, pressing Update starts a fresh engine, and the user gets
today's behaviour and today's two prompts. The fix degrades to the status quo rather than
to an error.

### 4.5 The window side

**The log is named as a run log from the start.** When `request_size` passes `--hold` it
passes `--log=<stamp>.log`, not `<stamp>.size.log`. A held preview may become the run, and
the engine writes its `--log=` value verbatim into `run.state` for run-following, so a run
that logged to a `.size.log` would be followed at a path the window's `_log_path` does not
name and "Open log file" would show the wrong file. Naming it correctly up front costs
nothing and needs no extra payload in `go.request`.

**`_launch`'s per-run reset is not part of starting a process, and adoption must run it
too.** `_launch` sets `_total`, the progress bar's range, `_run_active` and
`set_controls_enabled(False)`, and clears the per-run attributes, banners and badges. An
adopt path that only re-points `on_output`, `on_finished` and `on_error` ships a run with
no progress range, stale banners from the previous run, and `_run_active` false — which
leaves the standalone thin-snapshots action unguarded. So that reset block is factored out
of `_launch` and called by both paths.

**`_log_path` is excluded from the factored block, and that exclusion is the whole point of
the paragraph above.** `_launch` computes it from a fresh `datetime.now()` stamp, so a
shared block run on the adopt path would overwrite the log path with one no engine ever
wrote to — reintroducing the "Open log file" mismatch this section opens by forbidding, and
disagreeing with `run.state` line 2. The stamp and the `_log_path` assignment stay in
`_launch`; the adopt path keeps the path `request_size` already passed as `--log=`.

The window is then in exactly one of three states, and Update behaves differently in each:

| State | What Update does |
|---|---|
| No preview running | `_launch`, exactly as today |
| Preview running, no `hold.state` yet | **Wait** for `hold.state` or for the engine to exit, then re-enter this table. It must NOT write `go.request` — §4.3's freshness rule compares against a stamp that does not exist yet, so an early request is provably stale and would be ignored, leaving the user with a dead button |
| Preview running, `hold.state` present, and its line 1 is **this window's own `_size_proc` pid** | Run the reset block, write `go.request`, adopt `_size_proc` as `proc` |

That middle row is the whole dry run — seconds to a minute — and it is the state a user
who presses **Show download size** and then immediately presses **Update** is in.

`_launch` also gains the guard §2.3 found missing: it must not start a second engine while
`_size_proc` is live. And if the engine has gone by the time the window looks, the window
clears its held-engine state and falls back to `_launch` as it works today (INV-7).

### 4.6 The steps travel with the go-ahead

The preview is started for `system` alone, but the run uses whatever the user has selected
when they press Update, which may have changed in between. So the selection is written into
`go.request` rather than fixed at preview time, and the held engine runs what it is told.

**Every key in `go.request` must resolve in the engine's `LABEL` map, or the whole
go-ahead is refused and the hold ends as a Cancel.** `go.request` carries a step list and
nothing else; it must never become a route by which the window hands the engine a command
to run. The privilege boundary is otherwise unchanged — the window still never runs as
root (`docs/standards/security.md` §2).

**This is stricter than `--steps=`, deliberately, and reusing that path would be a
security defect.** `--steps=` does not validate: it iterates the five known keys calling
`step_selected`, so an unknown key is **silently dropped**, and the only rejection is when
*every* key is unknown (`if (( TOTAL == 0 ))` → exit 2). Reusing that behaviour would mean
a `go.request` reading `cache,../../evil` runs the cache step and reports success, which
is a file the window writes being partly ignored rather than refused. `--steps=` is a
flag a person types on their own command line; `go.request` is an authorisation read by a
root process, and the two do not warrant the same leniency.

## 5. Correctness invariants

- **INV-1** A size preview and the run that follows it cost exactly one interactive
  authentication between them.
  *Test:* `tests/run-tests.sh`, scenario "a size preview and a run that overlap cost exactly
  one password prompt" — committed and currently red, **and it must be rewritten before it
  can go green.** The committed form starts two engines by hand — `--size=system` in one
  process and `--steps=…` in another — and counts prompts across both. That reproduces
  today's defect, which is what it was written for, but no engine-side change can satisfy
  it: nothing in a held engine can stop a *separately launched* second engine calling
  `sudo_init`. §4 fixes the fault by having the **window** start one process, so the
  scenario must drive one engine with `--size=system --hold`, write a `go.request`, and
  assert one prompt across that single process. The committed red run is evidence about
  the defect, not about the rewritten scenario, whose own red run is still owed
  (`docs/standards/testing.md` §1).
  *Breaks when:* the run reaches `sudo_init` in a process that did not already
  authenticate — any change that starts a second engine for the run.

- **INV-2** A held engine never begins a transaction without a go-ahead newer than its own
  `hold.state`.
  *Test:* `tests/run-tests.sh` — hold with no `go.request`; the mock `zypper` exits 99 on a
  `dup` or `update` that does **not** carry `--dry-run`.
  *Breaks when:* the ceiling path falls through into the run instead of returning non-zero,
  or the staleness comparison is dropped and a leftover `go.request` is honoured.
  *Why the `--dry-run` carve-out:* the hold is only reached *after* `run_size`'s own
  `zypper … dup --allow-vendor-change --dry-run`. A mock exiting 99 on any `dup` fires
  during the size probe, so the scenario would die before it ever reached the hold — and
  per §6's last row that is "no hold at all", meaning the test could never exercise what it
  claims to.

- **INV-3** The hold ends without external help. No `go.request`, no `stop.request` and no
  window leaves the engine exited within `ONEUP_HOLD_SECONDS`, **exit status 0**.
  *Test:* `tests/run-tests.sh` — hold with `ONEUP_HOLD_SECONDS` set low; poll for exit and
  assert the status is 0 (§4.4: the size was delivered, so expiry is not a failure).
  *Breaks when:* the ceiling is unset, infinite, or only checked after a blocking read; or
  the dispatch propagates the hold's internal non-zero return to the caller.

- **INV-4** A `go.request` older than `hold.state` is ignored.
  *Test:* `tests/run-tests.sh` — write `go.request` first, then start the held engine, and
  assert no transaction ran.
  *Breaks when:* the freshness comparison is dropped, or leftovers are deleted at startup
  instead, which races a go-ahead pressed in the same moment.

- **INV-5** This work adds no marker **name**, so the marker reference's §5.1 freeze is not
  breached by a new marker.
  *Test:* `tests/run-tests.sh`, a census assertion running
  `grep -oE '\bmarker [A-Z_]+' update_system.sh | awk '{print $2}' | sort -u | wc -l`
  → `23`.
  *Breaks when:* the hold is signalled by a new marker rather than by `hold.state`.

- **INV-5a** This work changes no existing marker's **field layout**.
  *Test:* `tests/run-tests.sh` — harvest every `@@NAME@@|…` line a full mocked run emits,
  and assert each name's field count against a pinned table. A census cannot do this job:
  it counts distinct names, so it is blind to a field appended to an existing marker and
  blind to a rename, and gate G2 compares v1's stream against v2's, so a change made in
  both compares equal.
  *Breaks when:* a field is appended to an existing marker to carry hold state — the cheap
  change §5 of the marker reference explicitly invites, and the one this invariant exists
  to forbid for the duration of the freeze.

- **INV-6** The run performed after a go-ahead uses the step selection carried in
  `go.request`, not the step the preview was started for.
  *Test:* `tests/run-tests.sh` — preview `system`, go-ahead carrying `cache`; assert the
  `@@STEP_BEGIN@@` stream is the cache step.
  *Breaks when:* the held engine reuses its size step as its step list.

- **INV-7** When no held engine is available, pressing Update still starts a run. Expiry, a
  killed engine and a stale `hold.state` all degrade to today's behaviour, never to an
  error.
  *Test:* `tests/gui-smoke.py` — a window whose `_size_proc` has exited must still launch on
  Update.
  *Breaks when:* the window writes `go.request` and waits instead of falling back to
  `_launch`.

- **INV-8** `go.request` carries a step list and nothing else, and every key in it resolves
  in the engine's `LABEL` map before any step runs.
  *Test:* `tests/run-tests.sh` — a `go.request` carrying an unknown key, and one carrying
  shell metacharacters; assert the engine refuses the whole go-ahead and runs no step.
  *Breaks when:* the held engine expands the file's contents instead of matching each key
  against `LABEL`; or it reuses `--steps=`'s selection loop, which silently drops an
  unknown key and so would run the valid part of a tampered list and report success.

- **INV-9** A held run that becomes a real run spawns exactly ONE keep-alive, and `cleanup`
  kills it.
  *Test:* `tests/run-tests.sh` — extend the existing keep-alive scenario to the held path;
  after the run ends, assert no process carrying the `oneup-keepalive` tag survives.
  *Breaks when:* the held path re-enters `sudo_init`, whose second `setsid` overwrites
  `SUDO_KEEPALIVE` so `cleanup`'s group kill reaches only the later group. Nothing in the
  engine guards against this today — it is unreachable only because every existing
  `sudo_init` call site sits in a dispatch block that exits, and this design is the first
  thing that would put two of them on one process's path (ONEUP-0041,
  `docs/standards/security.md` §2.4).

## 6. Failure modes

| Assumption in §4 | When it breaks | What must happen |
|---|---|---|
| The window is alive to answer | It quits or crashes mid-hold | The engine exits at the ceiling or on the pid check; nothing is installed |
| The credential is still warm at go-ahead | The hold ran near the ceiling, or the keep-alive does not refresh this record (§10) | The run's first privileged call prompts — one extra dialog, never a failed run |
| The go-ahead arrives before the ceiling | The user deliberates for minutes | The engine has gone; the window falls back to `_launch` (INV-7) |
| `hold.state` is current | An earlier engine was `SIGKILL`ed and left one behind | Its line 1 is not this window's `_size_proc` pid, so §4.5 row 3 does not match and the window launches normally |
| One window | A second window opens mid-hold | The same test refuses it: with no `_size_proc` of its own it is in §4.5 row 1, so it launches its own engine rather than adopting a hold it did not start |
| The dry run succeeded | zypper errored, so no size was quoted | No hold at all — the existing failure path is unchanged |
| `go.request` carries a valid step list | A key does not resolve in `LABEL`, by tampering or by a window bug | The whole go-ahead is refused and the hold ends as a Cancel (INV-8) — never a partial run of the keys that happened to resolve |
| Update is pressed after `hold.state` exists | It is pressed during the dry run, before the stamp | The window waits for the stamp or for the engine to exit (§4.5); it does not write a `go.request` that its own freshness rule would discard |

## 7. Tests

Every scenario below must be seen to fail against the current tree before its fix lands
(`docs/standards/testing.md` §1), **and none of them has had that red run yet.** The
committed two-engine scenario is red, but it is red about the defect rather than about the
fix, and INV-1 explains why it cannot go green as written. So its rewritten one-engine form
owes a red run like every other scenario here.

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/run-tests.sh` — "a size preview and a run that overlap cost exactly one password prompt", **rewritten to drive one `--size=system --hold` engine and a `go.request`** |
| INV-2 | `tests/run-tests.sh` — hold scenario; the mock `zypper` exits 99 on a `dup`/`update` **without** `--dry-run` |
| INV-3 | `tests/run-tests.sh` — hold scenario with a low ceiling, asserting exit status 0 |
| INV-4 | `tests/run-tests.sh` — stale `go.request` scenario |
| INV-5 | `tests/run-tests.sh` — the marker-name census |
| INV-5a | `tests/run-tests.sh` — the per-marker field-count table |
| INV-6 | `tests/run-tests.sh` — preview one step, go-ahead another |
| INV-7 | `tests/gui-smoke.py` — fallback on an exited `_size_proc` |
| INV-8 | `tests/run-tests.sh` — unknown key, and metacharacters, in `go.request` |
| INV-9 | `tests/run-tests.sh` — the keep-alive scenario extended to the held path |
| §4.4's ceiling staying under sudo's credential lifetime | **nothing** — sudo's timeout is not readable without root and is asserted nowhere. If a user has lowered it, the hold silently costs a second prompt, which is INV-1's failure and no test would see it. Tracked in §10 |
| The structural count of privileged call sites (`security.md` §5.2) | `tests/run-tests.sh` — the existing call-site count assertion, which this work must update rather than route around |

### 7.1 One existing test mock must be corrected first

**The three counting mocks in `tests/run-tests.sh` model `sudo -k` more aggressively than
real sudo does, and that would fail a correct implementation of this spec.** Each contains
`for a in "$@"; do [[ "$a" == "-k" ]] && rm -f "$ts/ts.$PPID"; done`, so `-k` **deletes**
the cached timestamp. The engine records the opposite as measured, in `auth_current`'s own
comment: "-k does NOT invalidate a warm credential".

Today the divergence is invisible, because each process calls `auth_current` once before
its own `sudo_init`, when there is no timestamp to delete. It becomes visible the moment
one process reaches `sudo_init` twice — which is exactly what this design does. An
implementer who fell through without §4.2's suppression would see INV-1 still counting 2,
and the second prompt would be an artefact of the mock rather than the defect.

§4.2's suppression makes the second `auth_current` unreachable, so a conforming
implementation passes either way. The mocks are still wrong and should be corrected to
match the measured behaviour, so that the next design to reach `sudo_init` twice is not
misled by them.

**This was found by the cold review of this spec, not by a failing test.** It is a change
to committed test code rather than to this document, so it is surfaced rather than made
here.

## 8. Docs & release

Changed in the same release:

- `docs/reference/marker-protocol.md` §8 — the two new state files, and a note that the
  marker contract is deliberately untouched.
- `docs/specs/ONEUP-0054-python-engine.md` §4.1.1 — gains `hold.state` and `go.request`
  beside the two files it already pins, so the rewrite reproduces them.
- `docs/design/oneup-2.0.md` §6.2 — currently states the disproved one-invocation premise
  and says "no existing gate can see this bug". Both are now false.
- `CLAUDE.md` §4 — the state-directory paragraph names two files; it will name four.
- `docs/standards/files-and-naming.md` §5.1 — the override table opens "Every environment
  override that exists, and every path that has none", so `ONEUP_HOLD_STATE` and
  `ONEUP_GO_FILE` make it false the moment they land. Two rows, both **engine only**,
  beside the `ONEUP_RUN_STATE` and `ONEUP_STOP_FILE` rows they mirror.
- `docs/standards/security.md` §5.2 — if the privileged call-site count changes.
- `tests/run-tests.sh` — three changes, and only the last is optional here:
  - `run_engine` gains `ONEUP_HOLD_STATE` and `ONEUP_GO_FILE` defaults alongside the six
    it already sets. Without them every hold scenario below reads and writes the
    developer's real `~/.local/state/oneup/`, which is the default `docs/standards/testing.md`
    §2.1 records as having bitten twice for real.
  - INV-1's scenario rewritten to the one-engine `--hold` form, per INV-1 and §7.
  - the three counting mocks' `-k` handling, per §7.1. Not caused by this work and
    correctable independently of it.
- `README.md` — only if the download-size wording no longer matches what the user sees.
- `CHANGELOG.md`, and ONEUP-0044 on the roadmap.

No version-site change: this is not a release on its own.

## 9. Alternatives considered (and rejected)

- **Serialise the two launches and accept the second prompt.** Add the guard §2.3 found
  missing so the two dialogs can never be on screen together, and record the second as
  understood-and-accepted, which `docs/design/oneup-2.0.md` §6.2 does permit as a complete
  outcome. Rejected by the user on 2026-08-22. It is much the smaller change and fixes the
  confusing half, but it does not reach one authentication, so the scenario's assertion
  would have to be relaxed to match. **The guard itself is kept** — §4.5 adopts it.

- **Steer users to the ONEUP-0023 passwordless drop-in instead.** With it on there are no
  dialogs at all (§2.5). Rejected: it leaves the defect intact for everyone who declines,
  and making a security-relevant opt-in the remedy for a bug is the wrong pressure to put on
  that choice.

- **Make the preview unprivileged.** Rejected on measurement, not preference — §2.4.

- **Share sudo's credential between the two processes**, by giving them a common
  pseudo-terminal or by installing a `timestamp_type` default. Rejected: the second rewrites
  the user's system-wide sudo policy to work around an application bug, and the first is a
  pseudo-terminal hack whose failure mode is a silently unshared credential.

- **A new marker for the waiting state.** Rejected because the marker reference's §5.1
  forbids it until the rewrite has passed G2 — §4.1.

## 10. Out of scope

- **The Python engine's implementation of the hold** — ONEUP-0054 reproduces this contract
  like any other, and §4.3 is written so that it can.
- **Turning `HINT` and `REMEDY` payloads into codes** — ONEUP-0072.
- **Whether `sudo_init`'s keep-alive refreshes the credential record the engine actually
  uses.** The keep-alive is a `setsid bash -c '… sudo -n -v …'`, so its `sudo`'s parent is
  that shell rather than the engine — and with no terminal the timestamp is keyed to the
  parent pid. If that reasoning holds, the keep-alive has been refreshing a different record
  from the one the engine's own privileged calls use. It bears on §4.4: if the keep-alive
  does work, the ceiling could be longer. **Not verified, and deliberately not filed** —
  confirming it needs a real `sudo` and an interactive authentication, which
  `docs/standards/testing.md` §2.3 forbids the suite from doing.
- **Sudo's effective `timestamp_timeout` on a user's machine.** §4.4's 120 s is chosen to
  sit under the upstream default with margin, but the value is not readable without root and
  a user may have lowered it. §7 records that nothing catches this.
- **Whether a second window may adopt a hold it did not start.** §6 says no, on the grounds
  that a go-ahead is an authorisation and the window holding the size is the one the user is
  looking at. Recorded as a decision rather than settled by evidence.

## 11. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-08-22 | 3, cold; genre pinned `spec`; Q1 6 · Q2 3 · Q3 3 · Q4 2 — all 14 verified, 0 dismissed, all fixed | 6 | 3 | 3 | 2 | **Fourteen verified on the first loop, and the design section was where nearly all of them lived — §§1–3 and §9 came back clean.** **All three lanes independently found the same two defects**, which is the run's strongest signal. §4.2's pseudo-code said the hold would "read its steps, run them", while the prose two paragraphs down said the process "falls through into the ordinary run path" — two different mechanisms, and the first is impossible: the engine's step code is straight-line script *below* the `--size` dispatch, which the engine's own `system_txn_argv` comment already records. And INV-5's marker census cannot falsify its own second half — a distinct-name count is blind to a field appended to an existing marker, which is precisely the "cheap change" the marker reference invites, so the invariant claimed a coverage it did not have. Split into INV-5 and INV-5a, the latter given a real per-marker field-count assertion rather than a `nothing` row, since `documentation.md` §5 makes an untested invariant an incomplete spec by definition. **The most consequential finding was two lanes': "no second `sudo_init` is reached" was false.** Falling through reaches the main dispatch's `$needs_sudo && sudo_init`, which has no re-entry guard — and its second `setsid` overwrites `SUDO_KEEPALIVE`, so `cleanup`'s group kill reaches only the later group. That is ONEUP-0041's orphaned-keep-alive leak, and **this design would have been the first thing in the engine to make it reachable**: the same overwrite was checked and disproved as unreachable on this item three commits earlier, precisely because every existing call site sits in a dispatch block that exits. §4.2 now requires the held path to suppress it and INV-9 pins one keep-alive. **One finding was security-relevant.** §4.6 claimed `go.request`'s step keys are validated "exactly as `--steps=` already validates them" — and `--steps=` does not validate: it iterates the five known keys, so an unknown one is silently dropped and only an all-unknown set is refused (measured: `--steps=cache,bogus` runs cache and reports `@@DONE@@|ok`). A `go.request` is an authorisation read by a root process, so it now refuses the whole go-ahead on any key that does not resolve in `LABEL`. **Two more were contract gaps a builder could not have settled locally**: `hold.state` and `go.request` had contents but no line layout, while §10 claimed the Python engine could reproduce them and `run.state`'s equivalent is pinned line-by-line in ONEUP-0054 §4.1.1; and nothing said what the window does between starting the preview and the appearance of `hold.state` — a window of seconds to a minute in which §4.3's own freshness rule makes a `go.request` provably stale, i.e. exactly what a user pressing Update straight after Show download size would hit. **The gate also caught a defect in a fix it had just made.** 4a step 3's refuting run showed the replacement text asserted the engine detects a departed window by `$PPID` becoming 1 — and `reap_orphaned_askpass` carries the measurement that under systemd orphans reparent to `systemd --user`, so "an orphan-check against pid 1 silently never fires". Changed to capturing `WINDOW_PID` at startup and watching for a change. Two quotations added by fixes failed the verbatim check (hard wraps with `#` comment markers mid-quote) and were shortened to fragments that verify; substance unchanged, so not counted. **Surfaced rather than fixed, because it is committed test code**: the three counting mocks in `tests/run-tests.sh` delete the timestamp on `sudo -k`, where the engine records as measured that "-k does NOT invalidate a warm credential" — invisible today, and it would have made INV-1 fail a naive fall-through fix for a reason that is not the defect (§7.1). `spec_lint`'s 7 `missing_section` findings dismissed: the verb resolves the global spec-format standard, while this project pins its own eleven-section template in `documentation.md` §4 — the same run reports 8 of that class against ONEUP-0085, which is Implemented and converged. |
| 2 | 2026-08-23 | 3, cold; genre pinned `spec`; identical brief, packet rebuilt from disk; project's own `tests/docs-check.py` ran at 1d (20554 checked, 0 failed) | 2 | 2 | 2 | 1 | **Seven verified, seven fixed, none dismissed. Cap reached (2 for a spec); the run ships and implementation is the third reviewer.** **A calm cap, measured rather than recalled**: 3 of the 7 landed on text loop 1 wrote, and the two highest-value findings are original-draft defects, so the run was not repairing its own repairs. **All three lanes independently found the same defect, and the orchestrator had already found it building the packet** — §4.2's "a go-ahead sets `STEPS` and returns 0" is inert. The run path does not read `STEPS`: `RUN_KEYS`, `TOTAL`, `STEP_INDEX` and the `TOTAL == 0` rejection are all derived at script top level, far above the `--size` dispatch, and the run loop iterates `"${RUN_KEYS[@]}"`. Since `request_size` passes no `--steps=`, a go-ahead saying `cache` would have run **all five steps** — a full system upgrade the user never selected, and INV-6 falsified. Confirmed by running a structural model of the engine, not by reading it. §4.2 now spells out the whole adoption order. **The run's best finding was one lane's alone, and it is about the test this item has been resting on** [Q4]: INV-1's committed scenario starts two engines *by hand* and counts prompts across both, so **no engine-side change can ever satisfy it** — nothing in a held engine stops a separately launched one calling `sudo_init`. The scenario reproduces the defect, which is what it was written for, but it is not the fix's test; it must be rewritten to drive one `--size=system --hold` engine plus a `go.request`, and that form still owes its own red run. §7's claim that INV-1's red run "has been performed" was corrected to say none has. **The second [Q1] was loop 1's own repair failing the same way twice.** Loop 1 replaced a `$PPID`-against-1 test — dead because systemd reparents to `systemd --user` — with watching `$PPID` to CHANGE, which is dead for a different reason: bash sets `PPID` once at shell start and never refreshes it on reparenting. Measured: a child whose parent exited kept `$PPID=170203` for life while its real parent moved to `1309` (not `1`, which re-confirms the original warning). Now `kill -0 "$WINDOW_PID"`, the idiom `sudo_init`'s keep-alive already uses. **Both [Q2]s were two passages of §4.5 prescribing opposite things**: the factored reset block would overwrite `_log_path` with a fresh stamp, reintroducing the "Open log file" mismatch the paragraph directly above it exists to prevent; and the adopt row's condition ("`hold.state` present and its pid alive") was satisfied for a second window, which §6 forbids by name — it now keys on the window's own `_size_proc` pid, and §6's two rows were reconciled to that mechanism. **The [Q3]s were both things a builder could not settle locally**: whether `--hold` suppresses `run_size`'s `@@DONE@@` (it does — §4.9 makes `DONE` the only verdict for a *followed* run, so two in one stream reports `ok` before any step ran), and that `ONEUP_HOLD_STATE`/`ONEUP_GO_FILE` are registered nowhere — `files-and-naming.md` §5.1 opens "Every environment override that exists" and `run_engine` defaults six such vars, so without two more every hold scenario would read the developer's real state directory, the default `testing.md` §2.1 records as having bitten twice. **4a step 3 caught a defect in a fix as it was written**: the `@@DONE@@` replacement first asserted the window's `on_output` "treats `@@DONE@@` as the end of a run", and `handle_marker` only records `_done_status` while `on_finished` takes the verdict from the exit code. Corrected before it landed. **Four lane open questions resolved clean and are therefore outside the tally**: the `system_txn_argv` attribution is correct and my packet window had simply been cut above the comment; `auth_cmnds` does carry the `env LC_ALL=C zypper *` entry §2.5 relies on; no run *step* uses `sudo -n` (the three sites are the keep-alive, `cleanup` and `auth_current`), so §6 row 2's "one extra dialog, never a failed run" holds; and a `stop.request` left by a Cancel is ignored by both later consumers on their own stamp comparisons. |
