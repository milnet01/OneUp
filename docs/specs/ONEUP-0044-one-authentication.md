# ONEUP-0044 — One authentication for a size preview and the run that follows

**Status:** Draft
**Kind:** fix
**Roadmap:** ONEUP-0044
**Branch:** v2
**Verified at:** `bc0037a` — every claim naming a symbol below was resolved against this
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
does today up to and including its `@@SIZE@@` and `@@DONE@@` markers, and then, instead of
returning into the dispatch's `exit $?`, enters the hold:

```
hold_for_go_ahead()
  write   $HOLD_STATE_FILE          # pid, log path, the size just quoted
  poll    every $STOP_POLL_SECONDS, up to $ONEUP_HOLD_SECONDS:
            go.request   newer than hold.state -> read its steps, run them, return 0
            stop.request newer than hold.state -> return 1
            the window's pid is gone           -> return 1
  ceiling reached                              -> return 1
  always: rm -f $HOLD_STATE_FILE
```

On a go-ahead the process falls through into the ordinary run path holding the credential it
already has, so no second `sudo_init` is reached. On anything else it exits cleanly and the
window re-arms the size link exactly as `_on_size_finished` does today.

### 4.3 Two new state files, and one reused signal

Both live beside the existing two, in the directory the marker reference's §8 pins — the
engine's `ONEUP_STATE_DIR`, the window's `_state_home` — and both are overridable in the
engine only, matching the existing pair:

| File | Written by | Carries | Override |
|------|-----------|---------|----------|
| `hold.state` | the engine, when the hold begins | pid, log path, the quoted size | `ONEUP_HOLD_STATE` |
| `go.request` | the window, to say proceed | the step selection at the moment Update was pressed | `ONEUP_GO_FILE` |

**Cancel needs no new file.** `stop.request` already means "the user asked to stop" and both
halves already agree on it, so the window's Cancel writes that and the hold treats it as
`stop_pending` does.

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

**Expiry is not a failure.** The engine exits 0 having already delivered the size, the
window re-arms the link, and pressing Update then starts a fresh engine — today's behaviour,
today's two prompts. The fix degrades to the status quo rather than to an error.

### 4.5 The window side

- `request_size` passes `--hold` and, on `@@SIZE@@`, keeps `_size_proc` rather than letting
  `_on_size_finished` tear it down.
- Starting a run while a held engine exists writes `go.request` with the current step
  selection, then **adopts** `_size_proc` as `proc` — re-pointing `on_output`, `on_finished`
  and `on_error` at it — so every existing run path works unchanged.
- `_launch` gains the guard §2.3 found missing: it must not start a second engine while
  `_size_proc` is live.
- If `go.request` is written and the engine has already gone, the window falls back to
  `_launch` as it works today.

### 4.6 The steps travel with the go-ahead

The preview is started for `system` alone, but the run uses whatever the user has selected
when they press Update, which may have changed in between. So the selection is written into
`go.request` rather than fixed at preview time, and the held engine runs what it is told.

**The step keys are validated against the engine's existing `LABEL` map**, exactly as
`--steps=` already validates them. `go.request` carries a step list and nothing else; it
must never become a route by which the window hands the engine a command to run. The
privilege boundary is otherwise unchanged — the window still never runs as root
(`docs/standards/security.md` §2).

## 5. Correctness invariants

- **INV-1** A size preview and a run that are live at the same time cost exactly one
  interactive authentication between them.
  *Test:* `tests/run-tests.sh`, scenario "a size preview and a run that overlap cost exactly
  one password prompt" — already committed, and currently red.
  *Breaks when:* the run reaches `sudo_init` in a process that did not already
  authenticate — any change that starts a second engine for the run.

- **INV-2** A held engine never begins a transaction without a go-ahead newer than its own
  `hold.state`.
  *Test:* `tests/run-tests.sh` — hold with no `go.request`; the mock `zypper` exits 99 if it
  ever sees `dup` or `update`.
  *Breaks when:* the ceiling path falls through into the run instead of returning non-zero,
  or the staleness comparison is dropped and a leftover `go.request` is honoured.

- **INV-3** The hold ends without external help. No `go.request`, no `stop.request` and no
  window leaves the engine exited within `ONEUP_HOLD_SECONDS`.
  *Test:* `tests/run-tests.sh` — hold with `ONEUP_HOLD_SECONDS` set low; poll for exit.
  *Breaks when:* the ceiling is unset, infinite, or only checked after a blocking read.

- **INV-4** A `go.request` older than `hold.state` is ignored.
  *Test:* `tests/run-tests.sh` — write `go.request` first, then start the held engine, and
  assert no transaction ran.
  *Breaks when:* the freshness comparison is dropped, or leftovers are deleted at startup
  instead, which races a go-ahead pressed in the same moment.

- **INV-5** This work adds no marker and changes no marker's field layout, so the marker
  reference's §5.1 freeze holds and gate G2 still compares equal.
  *Test:* `grep -oE '\bmarker [A-Z_]+' update_system.sh | awk '{print $2}' | sort -u | wc -l`
  → `23`.
  *Breaks when:* the hold is signalled by a new marker rather than by `hold.state`.

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
  shell metacharacters; assert the engine refuses and runs no step.
  *Breaks when:* the held engine expands the file's contents instead of matching each key
  against `LABEL`.

## 6. Failure modes

| Assumption in §4 | When it breaks | What must happen |
|---|---|---|
| The window is alive to answer | It quits or crashes mid-hold | The engine exits at the ceiling or on the pid check; nothing is installed |
| The credential is still warm at go-ahead | The hold ran near the ceiling, or the keep-alive does not refresh this record (§10) | The run's first privileged call prompts — one extra dialog, never a failed run |
| The go-ahead arrives before the ceiling | The user deliberates for minutes | The engine has gone; the window falls back to `_launch` (INV-7) |
| `hold.state` is current | An earlier engine was `SIGKILL`ed and left one behind | The pid it carries is dead, so the window ignores it and launches normally |
| One window | A second window opens mid-hold | It must not adopt a hold it did not start; it launches its own engine |
| The dry run succeeded | zypper errored, so no size was quoted | No hold at all — the existing failure path is unchanged |

## 7. Tests

Every scenario below must be seen to fail against the current tree before its fix lands
(`docs/standards/testing.md` §1). INV-1's scenario is already committed and already red, so
it is the only one here whose red run has been performed; the rest are written with the fix.

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/run-tests.sh` — "a size preview and a run that overlap cost exactly one password prompt" |
| INV-2 | `tests/run-tests.sh` — hold scenario; the mock `zypper` exits 99 on any transaction |
| INV-3 | `tests/run-tests.sh` — hold scenario with a low ceiling |
| INV-4 | `tests/run-tests.sh` — stale `go.request` scenario |
| INV-5 | the marker census in INV-5, plus gate G2 |
| INV-6 | `tests/run-tests.sh` — preview one step, go-ahead another |
| INV-7 | `tests/gui-smoke.py` — fallback on an exited `_size_proc` |
| INV-8 | `tests/run-tests.sh` — unknown key, and metacharacters, in `go.request` |
| §4.4's ceiling staying under sudo's credential lifetime | **nothing** — sudo's timeout is not readable without root and is asserted nowhere. If a user has lowered it, the hold silently costs a second prompt, which is INV-1's failure and no test would see it. Tracked by ONEUP-0044 §10 |
| The structural count of privileged call sites (`security.md` §5.2) | `tests/run-tests.sh` — the existing call-site count assertion, which this work must update rather than route around |

## 8. Docs & release

Changed in the same release:

- `docs/reference/marker-protocol.md` §8 — the two new state files, and a note that the
  marker contract is deliberately untouched.
- `docs/specs/ONEUP-0054-python-engine.md` §4.1.1 — gains `hold.state` and `go.request`
  beside the two files it already pins, so the rewrite reproduces them.
- `docs/design/oneup-2.0.md` §6.2 — currently states the disproved one-invocation premise
  and says "no existing gate can see this bug". Both are now false.
- `CLAUDE.md` §4 — the state-directory paragraph names two files; it will name four.
- `docs/standards/security.md` §5.2 — if the privileged call-site count changes.
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
