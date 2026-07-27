# Testing Standard

**In one sentence:** a OneUp test must prove something a user would notice, must not care
what state the machine it runs on happens to be in, and must not damage that machine —
because the suite runs on the same computer OneUp updates, sometimes while a real update
is going on.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every count, path and symbol name below was measured against
the tree on 2026-07-26, not recalled.

**Sections:** 1 what the suite is · 2 isolation from the machine · 3 the mock-PATH sandbox ·
4 one invariant, one test · 5 the four correctness invariants · 6 determinism ·
7 a passing suite is silent · 8 new in 2.0 · 9 traps · 10 before you commit ·
what checks this · 11 cold-eyes log

## 1. What the suite is

Three programmes, each runnable on its own. All three are gated by `./local-CI.sh`, and all
three are the *only* gates GitHub CI also runs on a `v*` tag — everything else in
`local-CI.sh` is local-only (`docs/standards/workflow.md` §6):

| Suite | File | Asserts on |
| --- | --- | --- |
| Engine | `tests/run-tests.sh` | the `@@MARKER@@` lines `update_system.sh` prints |
| GUI | `tests/gui-smoke.py` | the window's state after being fed those same marker lines |
| Version bump | `tests/bump-test.py` | that a real bump still parses every version site, and rewrites the CHANGELOG heading and both links correctly (`docs/standards/workflow.md` §5.1's row owns the exact split) |

**No sizes or assertion counts appear here, deliberately**
(`docs/standards/documentation.md` §6b). They are wrong the next time anybody adds a test,
and wrong silently. **`./local-CI.sh` prints each suite's tally on every run**, which is
always current and is where to look. Where a count is genuinely needed as a baseline — the
figures 2.0 will be measured against — it belongs in the document doing the measuring, dated
and in the past tense: `docs/design/oneup-2.0.md` §2.

**`tests/docs-check.py` is a fourth programme in that directory and is deliberately not in
the table above.** It asserts nothing about what OneUp does — it checks the documentation
against the rules of `docs/standards/documentation.md`. It runs in `local-CI.sh` and, unlike
the three suites, **not** in GitHub CI (`docs/standards/workflow.md` §6 explains why the two
gate sets differ). Everything in §2 and §3 below is about the three suites; a rule that also
binds `docs-check.py` says so.

They meet in the middle: the engine suite proves the engine **emits** a marker, the GUI
suite proves the window **reacts** to it. Neither alone proves the pair works, which is why
a marker change touches both (`docs/reference/marker-protocol.md`).

The GUI suite exits **77** when PySide6 is absent, and both `local-CI.sh` and
`.github/workflows/release.yml` read that as *skipped*, not *failed* — the same
skip-cleanly-for-an-absent-tool convention the engine uses for `flatpak` and `fwupd`.

## 2. A test never depends on, or damages, the machine

This is the rule with the most scar tissue behind it, so it is first.

### 2.1 The three redirects

`run_engine` in `tests/run-tests.sh` rewrites three paths before every engine
invocation, each only if the scenario has not set it itself:

```bash
ONEUP_ZYPP_PID_FILE="${ONEUP_ZYPP_PID_FILE:-$mockdir/no-zypp.pid}"
ONEUP_RUN_STATE="${ONEUP_RUN_STATE:-$mockdir/run.state}"
ONEUP_STOP_FILE="${ONEUP_STOP_FILE:-$mockdir/stop.request}"
```

Both defaults bit for real, which is why the rule is not theoretical:

- The package-lock probe reads `/run/zypp.pid`. The suite went green to **40 failures**
  merely because the machine happened to be running zypper at the time — precisely the
  moment somebody is likely to be working on an update tool.
- `run.state` defaults to the user's own, and `cleanup` deletes the file it owns. Running
  the suite during a real update **deleted that run's record**, and the window could no
  longer find the run it was following (ONEUP-0045).

**A scenario that invokes the engine directly instead of through `run_engine` repeats all
three overrides by hand.** There is no fallback that catches the omission — the test simply
starts reading the machine's real state, and will pass or fail according to what the user
happens to be doing.

### 2.2 The GUI suite redirects the home directory

`tests/gui-smoke.py`'s module-level sandbox block points `HOME`, `XDG_CONFIG_HOME` and
`XDG_STATE_HOME` at a throwaway directory **before `QApplication` is constructed**, because `QSettings` resolves
its file path once and keeps it. Set them after and the test writes to the real
`~/.config`; `save_last_run()` then overwrites the user's own history with test data.

The same block puts a mock `notify-send` on `PATH` that appends to a log file,
so "a finished run notifies" is asserted without firing a desktop notification at whoever
is sitting in front of the machine.

### 2.3 No root, no network, ever

No test in this repository may:

- call real `sudo`, `pkexec`, or any privileged command;
- reach the network, including a package mirror, GitHub, or a DNS lookup;
- write outside its own `mktemp -d` directory or the redirected `HOME`.

**Two known exceptions exist today, and both are defects rather than carve-outs.** They
are named here because a rule with a silent exception is worse than a rule with a stated
one:

- **The GUI suite does reach the network.** `Updater.__init__` calls `_check_app_update`
  unconditionally, which issues a `QNetworkAccessManager` GET to `api.github.com` for the
  latest release. `tests/gui-smoke.py` constructs the window **49 times** and stubs
  nothing, so a run makes 49 live requests — rate-limitable, and silently dependent on a
  working connection. Filed as **ONEUP-0067**.
- **The engine suite does not redirect `HOME`.** `update_system.sh` runs
  `mkdir -p "$LOG_DIR"` with `LOG_DIR="$HOME/Documents/update-logs"`, so every scenario
  creates that directory on the real machine. The three `ONEUP_*` paths are redirected;
  `HOME` is not. Filed as **ONEUP-0058**.

The engine suite creates **75 throwaway directories and removes 75** — one per scenario
except the keep-alive-guard scenario, which needs none. A scenario adds `rm -rf "$d"` as
its last line, in the same block, not in a shared teardown — a shared teardown does not run
when a scenario is commented out during debugging.

## 3. The mock-PATH sandbox

Almost every engine scenario — 75 of 76 — builds a directory of fake system tools and
prepends it to `PATH`. (The exception is the keep-alive-guard scenario, which executes a
`sed`-extracted fragment of the engine rather than the engine, and is safe only because its
`kill -0` guard fails before the body runs. **Its safety rests on that guard and nothing
asserts the guard** — the suite does assert what the keep-alive *does* (it exits once the
engine is gone, SIGKILL and all), but not that this scenario's extracted fragment stays
harmless when it does not.)
`setup_common` in `tests/run-tests.sh` supplies the ones every scenario needs — `sudo`,
`systemctl`, `snapper`, `notify-send`, `flatpak`, `fwupdmgr` — and the scenario overwrites
whichever it needs to behave differently, usually `zypper`.

Three rules for writing a mock:

1. **Model the contract, not the tool.** The mock `zypper` is a `case` over `$*` that
   prints the handful of lines the engine parses. Do not reimplement zypper.
2. **Make the wrong behaviour loud.** A mock that must never be called a certain way exits
   **99** and prints why:

   ```bash
   # tests/run-tests.sh, scenario "--check reports counts read-only and never installs"
   [[ "$*" == *dup* || "$*" == *update* ]] && { echo "BUG: mutated in --check" >&2; exit 99; }
   ```

   There are **six** such traps today — in the two `--check` scenarios, the cache-clean
   scenario, both `--size=` scenarios and the passwordless-drop-in one. A silent wrong call is a test that passes for the wrong
   reason; an exit-99 is a test that says what it caught.
3. **Model the mechanism when the mechanism is the bug.** The one-prompt test's mock `sudo`
   (scenario: "a full run asks for the password exactly once") keeps **one timestamp file
   per parent pid**, because that is exactly how `sudoers(5)` `timestamp_type` behaves with
   no terminal, and the bug being locked out
   (ONEUP-0038) is a subshell changing the parent pid. A mock that just returned success
   would pass while the user got seven password popups.

## 4. One invariant, one test

Every `INV-N` in a spec names the test that locks it in
(`docs/standards/documentation.md` §5). The obligation runs both ways:

- **A spec invariant with no test is an incomplete spec**, not a spec with a follow-up.
- **A test with no invariant is fine** — plenty of assertions are ordinary coverage — but
  when a test exists precisely because a bug once shipped, say so in a comment naming the
  roadmap id, as the one-prompt scenario's preamble and `run_engine`'s own comment do. The
  comment is what stops the next person deleting the test as redundant.

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

Both suites do this nearly everywhere, and new tests copy the pattern:

```bash
# tests/run-tests.sh — wait for the thing, with a ceiling
for _ in $(seq 1 50); do grep -q '@@DONE@@' "$d/run.log" 2>/dev/null && break; sleep 0.1; done
```

```python
# tests/gui-smoke.py, _wait_for_notify — monotonic clock, so a clock change can't hang it
deadline = time.monotonic() + timeout
while time.monotonic() < deadline:
    if os.path.exists(_NOTIFY_LOG) and os.path.getsize(_NOTIFY_LOG) > 0:
        return True
    time.sleep(0.02)
```

A bare `sleep` is acceptable only **inside a mock**, where the delay is the thing being
simulated — for example the mirror that stalls (`sleep 30`, in the slow-source scenario),
the askpass that never returns (`sleep 300`, in the orphaned-dialog scenario), the
transaction slow enough for the keep-alive to be mid-sleep when it ends (`sleep 1`, in the
keep-alive scenario). Those are fixtures, not waits.

**One scenario breaks this rule and is the known exception**: the orphaned-dialog scenario
stages two background processes and then waits `sleep 0.5` **in the scenario body** before
`pgrep`-ing for their children. Worse, when that race is lost it takes a `SKIP` branch that
counts neither a pass nor a failure — so a run reported as green can quietly have made two
fewer assertions than the last one. Filed as **ONEUP-0068**. Do not copy the pattern; poll
for the child instead.

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

— and in between, **dozens of tracebacks**, every one of them:

```
RuntimeError: libshiboken: Internal C++ object (PySide6.QtCore.QProcess) already deleted.
```

They come from the `finished` lambda in `Updater._query_auth_status`. The cause is the
opposite of the obvious one: that `QProcess` **is** parented (`QProcess(self)`), and
parenting is what does it — the test drops the window, Qt deletes the child C++ object, and
the still-connected `finished` signal then fires into a Python wrapper whose C++ side is
gone. The suite is genuinely passing; the tracebacks are teardown, not failure. That is
precisely the problem — they are indistinguishable at a glance from that many real errors.

**The count is deliberately not stated** (`docs/standards/documentation.md` §6b). It varies
with teardown and garbage-collection order, so it differs between runs of the *same* commit
and drifts as the suite grows: four runs at `58ea3bc` gave 30, 30, 30, 31, and five at
`5e76cfb` gave 33, 32, 33, 33, 33. `ROADMAP.md`'s ONEUP-0062 headline says 56, which was one
observation and is now the third figure in circulation — the reason this section owns the
measurement and the roadmap bullet cites it. To see the current number:

```bash
python3 tests/gui-smoke.py 2>&1 | grep -c 'Traceback (most recent call last)'
```

**Do not assert on it.** §10's checklist asks for a traceback of a *new shape*, which is the
signal that survives the count changing.
Filed as **ONEUP-0062**, to be fixed in 2.0.

Two consequences for new tests. **An expected-error test asserts on the error and swallows
the output** rather than letting it print:

```python
try:
    w.handle_line(bad)
    check(f"malformed line handled: {bad[:22]!r}", True)
except Exception as exc:            # the assertion IS that this does not happen
    check(f"malformed line handled: {bad[:22]!r} ({exc})", False)
```

And **a test that cannot be made quiet says why in a comment, with a roadmap id.**

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

The 2.0 release gates (`docs/design/oneup-2.0.md` §7) add **six** suite-level obligations:
**G1** the engine suite passes with *no assertion changed*; **G2** v1 and v2 emit the same
marker stream under identical mocks; **G3** the GUI suite is green with the window driving
the new engine; **G4** a full run raises exactly one password prompt; **G5** the engine
imports no Qt and runs with PySide6 absent, enforced by test; **G10** the GUI suite passes
with the layout direction forced right-to-left.

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
- [ ] A green run of the whole suite prints no traceback of a *new shape* (the count of the known ONEUP-0062 ones varies run to run; a new message is the signal).
- [ ] If it locks in a spec invariant, the spec names it by file.
- [ ] `./local-CI.sh` is green.

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §2.1 the three redirects | `run_engine` applies them itself, so a scenario that goes through it cannot forget. A scenario that invokes the engine directly must repeat them by hand, and **nothing catches that** |
| §2.2 the GUI suite redirects `HOME` | the redirect is unconditional and module-level in `tests/gui-smoke.py`, so no individual test can forget it. **Nothing checks it still runs *before* `QApplication` is constructed** — and that ordering is the whole point, because `QSettings` resolves its path once and keeps it |
| §2.3 no root | the mock `PATH`: a real `sudo` is not on it, so a scenario that reaches for one gets the mock or nothing |
| §2.3 a test writes only inside its own temporary directory | **nothing — the engine suite breaks this.** `update_system.sh` builds `LOG_DIR` from `$HOME`, which `tests/run-tests.sh` does not redirect, so every scenario creates `~/Documents/update-logs` on the real machine (ONEUP-0058) |
| §2.3 no network | **nothing** — the GUI suite makes 49 live GitHub requests per run (ONEUP-0067) |
| §3 a mock fails loudly rather than quietly | several scenarios carry an `exit 99` trap. Nothing checks that a *new* mock has one |
| §4 one invariant, one test | nothing automatic |
| §5 the four correctness invariants | `tests/run-tests.sh` — this is what the suite is for, and the reason it exists |
| §6 poll for the condition, never sleep | **nothing** — one `sleep 0.5` remains in the orphaned-dialog scenario (ONEUP-0068) |
| §7 a passing suite is silent | **nothing** — the GUI suite prints dozens of teardown tracebacks while passing (ONEUP-0062). §7 says how to count them and why the number is not stated |

**Four rows name an open roadmap item instead of a gate**, and all four are places where the
suite does not yet obey its own standard. That is the honest picture, and it is the reason
each of the four is on the roadmap rather than in a footnote: §7 in particular is a rule this
suite breaks every single run.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: §2.3's no-network rule was flatly false (the GUI suite makes 49 live GitHub requests per run, now ONEUP-0067), the traceback count was neither 28 nor fixed, its stated cause was backwards, and "both suites already do this correctly" was contradicted by a `sleep 0.5` and a silent SKIP branch in the suite itself (ONEUP-0068) |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | none | clean. |
| 4 | 2026-07-26 | 1 critical, 1 medium — **2 verified** | the What-checks-this table said the GUI suite does not redirect `HOME`. It does; the **engine** suite is the one that does not, and the row had borrowed the engine's roadmap id. Two rules, two failures, one row — and the table read as authoritative while saying the opposite of the truth. |
| 5 | 2026-07-26 | 2 medium — **0 verified, 2 dismissed** | both asked that §2.3's absolute *no test may reach the network* be softened to *should not*, because the section then names its own violations. That disclosure is deliberate, and the proposed wording is the uncheckable hedge `documentation.md` §8.1 bans. Dismissed explicitly rather than filtered. |
| 6 | 2026-07-26 | 1 medium — **1 verified** | converged (polish only). §3's parenthetical pointed at §2.1 for a claim §2.1 does not make, and blurred what the suite does assert about the keep-alive against what it does not. |
