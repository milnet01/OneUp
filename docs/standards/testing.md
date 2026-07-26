# Testing Standard

**In one sentence:** a OneUp test must prove something a user would notice, must not care
what state the machine it runs on happens to be in, and must not damage that machine —
because the suite runs on the same computer OneUp updates, sometimes while a real update
is going on.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `416caa4` — every count, path and line number below was measured against
the tree on 2026-07-26, not recalled.

## 1. What the suite is

Three programmes, all runnable on their own, all gated by `./local-CI.sh` and by GitHub CI
on a `v*` tag:

| Suite | File | Size | Asserts on |
| --- | --- | --- | --- |
| Engine | `tests/run-tests.sh` | 2,041 lines, **76 scenarios**, 205 assertions | the `@@MARKER@@` lines `update_system.sh` prints |
| GUI | `tests/gui-smoke.py` | 1,361 lines, 283 assertions | the window's state after being fed those same marker lines |
| Version bump | `tests/bump-test.py` | 95 lines, 6 assertions | that `bump.py` rewrites all six version sites |

They meet in the middle: the engine suite proves the engine **emits** a marker, the GUI
suite proves the window **reacts** to it. Neither alone proves the pair works, which is why
a marker change touches both (`docs/reference/marker-protocol.md`, once Task 9 lands).

The GUI suite exits **77** when PySide6 is absent, and both `local-CI.sh:49` and
`.github/workflows/release.yml:38` read that as *skipped*, not *failed* — the same
skip-cleanly-for-an-absent-tool convention the engine uses for `flatpak` and `fwupd`.

## 2. A test never depends on, or damages, the machine

This is the rule with the most scar tissue behind it, so it is first.

### 2.1 The three redirects

`run_engine` (`tests/run-tests.sh:56`) rewrites three paths before every engine
invocation, each only if the scenario has not set it itself:

```bash
ONEUP_ZYPP_PID_FILE="${ONEUP_ZYPP_PID_FILE:-$mockdir/no-zypp.pid}"
ONEUP_RUN_STATE="${ONEUP_RUN_STATE:-$mockdir/run.state}"
ONEUP_STOP_FILE="${ONEUP_STOP_FILE:-$mockdir/stop.request}"
```

Both defaults bit for real, which is why the rule is not theoretical:

- The package-lock probe reads `/run/zypp.pid`. **40 scenarios failed** merely because the
  machine happened to be running zypper at the time — precisely the moment somebody is
  likely to be working on an update tool.
- `run.state` defaults to the user's own, and `cleanup` deletes the file it owns. Running
  the suite during a real update **deleted that run's record**, and the window could no
  longer find the run it was following (ONEUP-0045).

**A scenario that invokes the engine directly instead of through `run_engine` repeats all
three overrides by hand.** There is no fallback that catches the omission — the test simply
starts reading the machine's real state, and will pass or fail according to what the user
happens to be doing.

### 2.2 The GUI suite redirects the home directory

`tests/gui-smoke.py:29-32` points `HOME`, `XDG_CONFIG_HOME` and `XDG_STATE_HOME` at a
throwaway directory **before `QApplication` is constructed**, because `QSettings` resolves
its file path once and keeps it. Set them after and the test writes to the real
`~/.config`; `save_last_run()` then overwrites the user's own history with test data.

The same block puts a mock `notify-send` on `PATH` (`:34-43`) that appends to a log file,
so "a finished run notifies" is asserted without firing a desktop notification at whoever
is sitting in front of the machine.

### 2.3 No root, no network, ever

No test in this repository may:

- call real `sudo`, `pkexec`, or any privileged command;
- reach the network, including a package mirror, GitHub, or a DNS lookup;
- write outside its own `mktemp -d` directory or the redirected `HOME`.

The engine suite creates **75 throwaway directories and removes 75**. A scenario adds
`rm -rf "$d"` as its last line, in the same block, not in a shared teardown — a shared
teardown does not run when a scenario is commented out during debugging.

## 3. The mock-PATH sandbox

Every engine scenario builds a directory of fake system tools and prepends it to `PATH`.
`setup_common` (`tests/run-tests.sh:16`) supplies the ones every scenario needs — `sudo`,
`systemctl`, `snapper`, `notify-send`, `flatpak`, `fwupdmgr` — and the scenario overwrites
whichever it needs to behave differently, usually `zypper`.

Three rules for writing a mock:

1. **Model the contract, not the tool.** The mock `zypper` is a `case` over `$*` that
   prints the handful of lines the engine parses. Do not reimplement zypper.
2. **Make the wrong behaviour loud.** A mock that must never be called a certain way exits
   **99** and prints why:

   ```bash
   # tests/run-tests.sh:294 — --check must never mutate the system
   [[ "$*" == *dup* || "$*" == *update* ]] && { echo "BUG: mutated in --check" >&2; exit 99; }
   ```

   There are five such traps today (`:294`, `:390`, `:414`, `:442`, `:1268`). A silent
   wrong call is a test that passes for the wrong reason; an exit-99 is a test that says
   what it caught.
3. **Model the mechanism when the mechanism is the bug.** The one-prompt test's mock `sudo`
   (`:526`) keeps **one timestamp file per parent pid**, because that is exactly how
   `sudoers(5)` `timestamp_type` behaves with no terminal, and the bug being locked out
   (ONEUP-0038) is a subshell changing the parent pid. A mock that just returned success
   would pass while the user got seven password popups.

## 4. One invariant, one test

Every `INV-N` in a spec names the test that locks it in
(`docs/standards/documentation.md` §5). The obligation runs both ways:

- **A spec invariant with no test is an incomplete spec**, not a spec with a follow-up.
- **A test with no invariant is fine** — plenty of assertions are ordinary coverage — but
  when a test exists precisely because a bug once shipped, say so in a comment naming the
  roadmap id, as `:512` and `:65` do. The comment is what stops the next person deleting
  the test as redundant.

When an invariant is withdrawn, its test is deleted in the same commit. A test kept
"just in case" after the rule it proved is gone will eventually fail for a reason nobody
can interpret.

## 5. The four correctness invariants that must never regress

The engine suite exists mainly to protect one class of bug — **a step must never claim
success, or advise a reboot, that it did not earn.** These four are the floor. Changing
engine logic without re-checking them is how the original bug returns:

1. **Reboot advice (`@@REBOOT@@|yes`) fires only when something was actually installed, or
   `zypper needs-rebooting` explicitly says so** — never merely because a step errored.
2. **A failed step is recorded, emits a plain-English `@@HINT@@`, and the run continues**
   to the next step, so cache cleanup still happens and the summary is still useful.
3. **A package-only change offers a service restart (`@@SERVICES@@`), not a reboot.**
4. **`--check` is strictly read-only and runs without root** — no `zypper dup`, no
   `zypper update`; the mock exits 99 if either is called.

## 6. Waiting: poll for the condition, never sleep for a duration

A test that sleeps long enough "on this machine" is a test that fails on a loaded CI
runner and passes again on a re-run — the worst kind, because a flake trains people to
re-run rather than read.

Both suites already do this correctly, and new tests copy the pattern:

```bash
# tests/run-tests.sh:716 — wait for the thing, with a ceiling
for _ in $(seq 1 50); do grep -q '@@DONE@@' "$d/run.log" 2>/dev/null && break; sleep 0.1; done
```

```python
# tests/gui-smoke.py:85 — same shape, monotonic clock so a clock change can't hang it
deadline = time.monotonic() + timeout
while time.monotonic() < deadline:
    if os.path.exists(_NOTIFY_LOG) and os.path.getsize(_NOTIFY_LOG) > 0:
        return True
    time.sleep(0.02)
```

A bare `sleep` is acceptable only **inside a mock**, where the delay is the thing being
simulated — a mirror that stalls (`:801`, `sleep 30`), an askpass that never returns
(`:644`, `sleep 300`), a transaction slow enough for the keep-alive to be mid-sleep when it
ends (`:1500`). Those are fixtures, not waits.

Determinism also means: no dependence on wall-clock time of day, on the order a real
filesystem returns entries, or on any network at all.

## 7. A passing suite is silent

**A green run prints nothing but its own results.** Noise in a passing suite trains you to
skim past output, and the one run where the noise is a real regression looks exactly like
the previous hundred.

The live counter-example, measured 2026-07-26 at `416caa4`:

```console
$ QT_QPA_PLATFORM=offscreen python3 tests/gui-smoke.py
...
  Passed: 283   Failed: 0
$ echo $?
0
```

— and in between, **28 tracebacks**, every one of them:

```
RuntimeError: libshiboken: Internal C++ object (PySide6.QtCore.QProcess) already deleted.
```

They come from a `finished` lambda (`updater.py:2461`) firing after Python has dropped the
last reference to the `QProcess`, so the C++ object is gone while the wrapper is not. The
suite is genuinely passing; the tracebacks are teardown, not failure. That is precisely the
problem — they are indistinguishable at a glance from 28 real errors. Filed as
**ONEUP-0062**, to be fixed in 2.0.

Two consequences for new tests: an expected-error test asserts on the error and swallows
the output rather than letting it print, and a test that cannot be made quiet says why in a
comment, with a roadmap id.

## 8. New in 2.0: unit tests become possible

The Bash engine can only be tested end-to-end — there is no way to call `progress_filter`
with a line and inspect what it returns without running a whole scenario. The Python engine
(ONEUP-0054) changes that, and the suite should take the offer:

- **Unit-test the parsers.** zypper's `Retrieving: … (12/77)`, `( 7/77) Installing:`,
  `Preloading:`, `Package download size:` / `Overall download size:` — one function, a
  table of input lines, a table of expected values. Every wording variant gets a row,
  including the ones that exist because two zypper backends print differently.
- **Keep the end-to-end scenario anyway.** The unit test proves the parser; only the
  scenario proves the parser is wired to the marker that the GUI reads. Deleting the
  scenario because "the unit test covers it" removes the only proof of the contract.
- **Do not unit-test through the mock PATH.** If a function can be called directly, call it
  directly; the sandbox is for things that must spawn a process.

The 2.0 release gates (`docs/design/oneup-2.0.md` §7) add four suite-level obligations:
**G1** the engine suite passes with *no assertion changed*; **G2** v1 and v2 emit the same
marker stream under identical mocks; **G4** a full run raises exactly one password prompt;
**G5** the engine imports no Qt, enforced by test; **G10** the GUI suite passes with the
layout direction forced right-to-left.

## 9. Traps

- **"I'll just run it against the real thing to check."** That is how `/run/zypp.pid` and
  `run.state` got read for real. There is no *quick* exception to §2 — the quick version is
  the version that deleted a user's run record.
- **A mock that returns success for everything.** It makes any test pass, including the one
  that was supposed to catch the bug. Ask what the mock would have to do to *fail* the
  test, and make sure it can.
- **Asserting on a substring that is too short.** `check` matches with `grep -qF`, so
  asserting `"@@REBOOT@@"` passes on `@@REBOOT@@|no`. Assert the whole field layout,
  including the value — `"@@REBOOT@@|yes"`.
- **Testing the mock instead of the engine.** If changing the engine cannot make the
  assertion fail, the test proves nothing. Confirm a new test fails before it passes.
- **A shared teardown.** Scenarios are commented out one at a time while debugging (there
  is no per-test selector); cleanup that lives outside the scenario body is skipped exactly
  when the debugging is happening.
- **Adding a gate to one CI and not the other.** `local-CI.sh` and
  `.github/workflows/release.yml` must stay in step; a gate in only one of them is a gate
  that half of the pushes ignore.

## 10. Before you commit a test change

- [ ] It runs with no network and no root, and touches nothing outside its temp directory.
- [ ] If it invokes the engine directly, all three `ONEUP_*` paths are redirected.
- [ ] Its mock fails loudly (exit 99) on the behaviour it is guarding against.
- [ ] It waits by polling for a condition, not by sleeping for a duration.
- [ ] It fails before the fix and passes after — verified, not assumed.
- [ ] A green run of the whole suite prints no tracebacks it did not already print.
- [ ] If it locks in a spec invariant, the spec names it by file.
- [ ] `./local-CI.sh` is green.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| — | — | *not yet run* | scheduled as batch 1 (`docs/plans/ONEUP-0057-documentation-set.md`, Task 10) |
