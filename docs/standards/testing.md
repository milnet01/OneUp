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

Each is runnable on its own, and all are gated by `./local-CI.sh`. Which of them GitHub CI
also runs on a `v*` tag is `docs/standards/workflow.md` §6's to state.

| Suite | File | Asserts on |
| --- | --- | --- |
| Engine | `tests/run-tests.sh` | the `@@MARKER@@` lines the engine prints — the `oneup.engine` package by default since ONEUP-0054 stage 9, any other command through `ONEUP_ENGINE_CMD` |
| Engine parsers | `tests/parsers-test.py` | the pure half of the engine, `oneup/engine/parsers.py`, table-driven against real captured zypper output and the lock file's text |
| GUI | `tests/gui-smoke.py` | the window's state after being fed those same marker lines — and one scenario that launches the Python engine through the window's own code path and asserts the window acted on what the engine actually sent (gate G3 of ONEUP-0054). Run twice by both gates: the second time as `tests/gui-smoke.py -reverse`, mirrored right-to-left, whose first assertion is that it really is (ONEUP-0032 INV-5) |
| Version bump | `tests/bump-test.py` | that a real bump still parses the five real version sites, and rewrites the CHANGELOG heading and both links correctly (`docs/standards/workflow.md` §5.1's row owns the exact split) |
| Package structure | `tests/imports-test.py` | the `oneup/` package's structural rules — how path constants are imported, which way the engine and window may depend on each other, and how the engine is launched (`docs/standards/workflow.md` §6's row names each) |
| Translation groundwork | `tests/i18n-check.py` | the source rules that keep the window translatable and mirrorable — ONEUP-0032's source-level invariants, each named in the suite's header |

**No sizes or assertion counts appear here, deliberately**
(`docs/standards/documentation.md` §6b). They are wrong the next time anybody adds a test,
and wrong silently. **`./local-CI.sh` prints each suite's tally on every run**, which is
always current and is where to look. Where a count is genuinely needed as a baseline — the
figures 2.0 will be measured against — it belongs in the document doing the measuring, dated
and in the past tense: `docs/design/oneup-2.0.md` §2.

**`tests/docs-check.py` is one more programme in that directory and is deliberately not in
the table above.** It asserts nothing about what OneUp does — it checks the documentation
against the rules of `docs/standards/documentation.md`. It runs in `local-CI.sh` and, unlike
the test suites, **not** in GitHub CI (`docs/standards/workflow.md` §6 explains why the two
gate sets differ). Everything in §2 and §3 below is about the suites in the table; a rule that also
binds `docs-check.py` says so.

They meet in the middle: the engine suite proves the engine **emits** a marker, the GUI
suite proves the window **reacts** to it. Neither alone proves the pair works, which is why
a marker change touches both (`docs/reference/marker-protocol.md`).

The GUI suite exits **77** when PySide6 is absent, and both `local-CI.sh` and
`.github/workflows/release.yml` read that as *skipped*, not *failed* — the same
skip-cleanly-for-an-absent-tool convention the engine uses for `flatpak` and `fwupd`.

## 2. A test never depends on, or damages, the machine

This is the rule with the most scar tissue behind it, so it is first.

### 2.1 The redirects

`run_engine` in `tests/mock-env.sh`, which `tests/run-tests.sh` sources, rewrites every
state path the engine reads, before each invocation and only where the scenario has not set
it itself:

```bash
ONEUP_ZYPP_PID_FILE="${ONEUP_ZYPP_PID_FILE:-$mockdir/no-zypp.pid}"
ONEUP_RUN_STATE="${ONEUP_RUN_STATE:-$mockdir/run.state}"
ONEUP_STOP_FILE="${ONEUP_STOP_FILE:-$mockdir/stop.request}"
ONEUP_HOLD_STATE="${ONEUP_HOLD_STATE:-$mockdir/hold.state}"
ONEUP_GO_FILE="${ONEUP_GO_FILE:-$mockdir/go.request}"
ONEUP_GUARD_FILE="${ONEUP_GUARD_FILE:-$mockdir/oneup-download-guard}"
ONEUP_INHIBITED="${ONEUP_INHIBITED-1}"
ONEUP_REPOS_DIR="${ONEUP_REPOS_DIR:-$mockdir/repos.d}"
```

It also puts the mock directory first on `PATH`, and passes `--log=` into the scenario
directory so the engine never defaults into a log directory under the real `HOME`.

**The rule is every override, not a fixed count — read the set out of `run_engine`.**
ONEUP-0044 added `hold.state` and `go.request` after this section was written, and the
count in this prose stayed at four; a scenario copying that list would read and write the
developer's real state directory, which is the exact damage §2 exists to prevent.

`ONEUP_GUARD_FILE` is ONEUP-0092's, and it is here for the same reason as the first:
`guard_current` **reads** that path on every run that reaches the download pass, so without
a default the suite's result would depend on whether the developer's own machine happens to
have OneUp's passwordless setting granted.

`ONEUP_INHIBITED` is the one that is not a path. Without it the engine re-runs itself under
`systemd-inhibit` and takes a real shutdown lock on the developer's own session
(ONEUP-0086). It uses `-`, not `:-`, so a scenario opts back in by setting it empty.

Both defaults bit for real, which is why the rule is not theoretical:

- The package-lock probe reads `/run/zypp.pid`. The suite went green to **40 failures**
  merely because the machine happened to be running zypper at the time — precisely the
  moment somebody is likely to be working on an update tool.
- `run.state` defaults to the user's own, and `cleanup` deletes the file it owns. Running
  the suite during a real update **deleted that run's record**, and the window could no
  longer find the run it was following (ONEUP-0045).

**A scenario that invokes the engine directly instead of through `run_engine` repeats every
one of those settings by hand.** There is no fallback that catches the omission — the test simply
starts reading the machine's real state, and will pass or fail according to what the user
happens to be doing.

### 2.2 The GUI suite redirects the home directory

`tests/gui-smoke.py`'s module-level sandbox block points `HOME`, `XDG_CONFIG_HOME` and
`XDG_STATE_HOME` at a throwaway directory **before the window's modules are imported**, and
so before `QApplication` is constructed. Both bounds bind: `oneup/gui/paths.py` computes every
state path once, at import, and `QSettings` resolves its file once and keeps it. Set them
after and the test writes to the real `~/.config`, and `save_last_run()` overwrites the
user's own history with test data.

The same block puts a mock `notify-send` on `PATH` that appends to a log file,
so "a finished run notifies" is asserted without firing a desktop notification at whoever
is sitting in front of the machine.

### 2.3 No root, no network, ever

No test in this repository may:

- call real `sudo`, `pkexec`, or any privileged command;
- reach the network, including a package mirror, GitHub, or a DNS lookup;
- write outside its own `mktemp -d` directory or the redirected `HOME`.

**The GUI suite meets the network rule by stubbing, and where the stub sits is the whole of
it.** `Updater.__init__` calls `_check_app_update`, which issues a `QNetworkAccessManager`
GET to `api.github.com` for the latest release, and `tests/gui-smoke.py` constructs the
window dozens of times. So `main()` replaces `app_update._check_app_update` — the module function the window
calls, not a method of it — with a no-op **before its
first `updater.Updater()`**. Unauthenticated GitHub allows 60 calls an hour per address:
before the stub, one run spent 56 of them and a few runs exhausted for real the budget the
app's own *Check for updates* button needs (**ONEUP-0090**, which also closed the earlier
duplicate ONEUP-0067). Nothing in the suite asserts on the check or its reply handler, so
the stub costs no coverage — but a window constructed above that line restores the defect
silently, and nothing catches that.

**Two exceptions exist today. One is a defect and one is a deliberate carve-out**, and the
difference between those is the point — a rule with a silent exception is worse than a rule
with a stated one:

- **The engine suite does not redirect `HOME`, on either branch.** *A defect on `main`;
  closed on `v2`.* The `ONEUP_*` paths are redirected and `HOME` is not, so what
  decides the outcome is when the engine makes its log directory. On `main`
  `update_system.sh` runs `mkdir -p "$LOG_DIR"` — `LOG_DIR="$HOME/Documents/update-logs"` —
  before it has looked at `--log=`, so every scenario creates that directory on the real
  machine. On `v2` both engines create it only when about to default into it, so nothing
  appears, and a scenario asserts that. Filed as **ONEUP-0058**, closed by ONEUP-0054
  stage 2; `main` is frozen and keeps the old shape.
- **One engine scenario reaches the network on purpose.** *A carve-out.* ONEUP-0094's T-1
  asks the real openSUSE content CDN for a repository-metadata file and asserts HTTP 200,
  because the item's whole claim is that a named third-party host is still there — a mock
  would assert only that the mock was written correctly. It is gated on
  `ONEUP_TEST_NETWORK=1` and SKIPs loudly without it, so the rule above holds for every run
  that does not opt in. **Exactly one run opts in: `./local-CI.sh` invoked by hand.** The
  release workflow calls `tests/run-tests.sh` directly, and `githooks/pre-push` passes
  `ONEUP_TEST_NETWORK=0` to the `local-CI.sh` it runs — **which it did not do until
  2026-08-07**, so until then a push was gated on somebody else's server being up, the one
  outcome the split exists to prevent (**ONEUP-0097**). That is the shape to watch for: the
  hook did not opt in anywhere you could read, it inherited the opt-in by running a script
  that had one. **A second such scenario needs the same three properties** — a claim about a
  real external service, an opt-in gate, and a loud SKIP — or it is a breach, not a
  precedent.

The engine suite creates **one throwaway directory per scenario that needs one, and removes
every one**. The invariant is the
*pairing*, not a total: every `X=$(mktemp -d)` has an `rm -rf "$X"`, and a scenario that
adds the first without the second is the leak this rule exists to catch. Two totals cannot
show it — the suite's own directories are not all called `$d`. A scenario adds the removal as
its last line, in the same block, not in a shared teardown — a shared teardown does not run
when a scenario is commented out during debugging.

## 3. The mock-PATH sandbox

Almost every engine scenario builds a directory of fake system tools and prepends it to
`PATH`.
`setup_common` in `tests/mock-env.sh` supplies the ones every scenario needs — `sudo`,
`systemctl`, `snapper`, `notify-send`, `flatpak`, `fwupdmgr`, `df` — and the scenario
overwrites whichever it needs to behave differently, usually `zypper`.

`df` is on that list for the same reason §2.1's `ONEUP_*` paths are redirected, and it
was added on 2026-08-03 for the same reason they were: the pre-flight low-disk check reads
the real filesystem, so on a machine under the 2 GiB threshold every system-step scenario
gained a real `@@DISK@@|warn` line sourced from whatever the developer's disk happened to
be doing. A scenario that wants the warning overwrites the mock, exactly as it would
`zypper`.

`setup_cached_sudo` sits beside it and is the one variant several scenarios need: it
replaces `setup_common`'s sudo with one whose `-n` probe *succeeds*, modelling a box where
an earlier interactive validate already warmed the credential — which is what `cleanup()`'s
restore relies on, since it must never block on a password dialog inside the trap.

Three rules for writing a mock:

1. **Model the contract, not the tool.** The mock `zypper` is a `case` over `$*` that
   prints the handful of lines the engine parses. Do not reimplement zypper.
2. **Make the wrong behaviour loud.** A mock that must never be called a certain way exits
   **99** and prints why:

   ```bash
   # tests/run-tests.sh, scenario "--check reports counts read-only and never installs"
   [[ "$*" == *dup* || "$*" == *update* ]] && { echo "BUG: mutated in --check" >&2; exit 99; }
   ```

   The `--check`, cache-clean and `--size=` scenarios carry such a trap, among others. A silent wrong call is a test that passes for the wrong
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
2. **A failed step is recorded, emits a `@@HINT@@` the window words in plain English, and
   the run continues** to the next step, so cache cleanup still happens and the summary is still useful.
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

They come from the `finished` lambda in `_query_auth_status` (`oneup/gui/auth.py`). The
cause is the opposite of the obvious one: that `QProcess` **is** parented (`QProcess(win)`), and
parenting is what does it — the test drops the window, Qt deletes the child C++ object, and
the still-connected `finished` signal then fires into a Python wrapper whose C++ side is
gone. The suite is genuinely passing; the tracebacks are teardown, not failure. That is
precisely the problem — they are indistinguishable at a glance from that many real errors.

**The count is deliberately not stated** (`docs/standards/documentation.md` §6b). It varies
with teardown and garbage-collection order, so it differs between runs of the *same* commit
and drifts as the suite grows: four runs at `58ea3bc` gave 30, 30, 30, 31, and five at
`5e76cfb` gave 33, 32, 33, 33, 33. This section owns the measurement. To see the current number:

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

The Bash engine could only be tested end-to-end — there was no way to call `progress_filter`
with a line and inspect what it returns without running a whole scenario. The Python engine
(ONEUP-0054) changed that, and the suite should take the offer:

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
**G1** the engine suite passes with no existing assertion weakened (design §7 states exactly which suite changes it permits); **G2** v1 and v2 emit the same
marker stream under identical mocks; **G3** the GUI suite is green with the window driving
the new engine; **G4** a full run authenticates exactly once — not the same as one dialog (design §6.2); **G5** the engine
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
- **Adding a *test* gate to one CI and not the other.** `docs/standards/workflow.md` §10
  owns this trap and §6 owns the policy behind it, including why the non-test gates stay
  local deliberately.

## 10. Before you commit a test change

- [ ] It runs with no network and no root, and touches nothing outside its temp directory.
- [ ] If it invokes the engine directly, it repeats everything `run_engine` sets up — the
  `ONEUP_*` overrides, the `PATH` prefix and `--log=` (§2.1).
- [ ] Its mock fails loudly (exit 99) on the behaviour it is guarding against.
- [ ] It waits by polling for a condition, not by sleeping for a duration.
- [ ] It fails before the fix and passes after — verified, not assumed.
- [ ] A green run of the whole suite prints no traceback of a *new shape* (the count of the known ONEUP-0062 ones varies run to run; a new message is the signal).
- [ ] If it locks in a spec invariant, the spec names it by file.
- [ ] `./local-CI.sh` is green.

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §2.1 the redirects | `run_engine` applies them itself, so a scenario that goes through it cannot forget. A scenario that invokes the engine directly must repeat them by hand, and **nothing catches that** — nor does anything catch this list going stale, which it has twice |
| §2.2 the GUI suite redirects `HOME` | the redirect is unconditional and module-level in `tests/gui-smoke.py`, so no individual test can forget it. **Nothing checks it still runs before the window's modules are imported** — and that ordering is the whole point, because `oneup/gui/paths.py` computes every state path at import |
| §2.3 no root | **half-covered.** `run_engine` puts the mock directory in front of the real `PATH`, so a name the scenario mocks — `setup_common` mocks `sudo` — shadows the real one. The real tools are still behind it: a scenario without `setup_common`, an absolute path, or `pkexec` (mocked nowhere) reaches the real binary, and nothing catches that |
| §2.3 a test writes only inside its own temporary directory | **on `v2`, the ONEUP-0058 scenario** — it redirects `HOME` and asserts no log directory appears when `--log=` points elsewhere. **On `main`, nothing:** `update_system.sh` there builds `LOG_DIR` from `$HOME` and creates it before looking at `--log=`, and `tests/run-tests.sh` does not redirect `HOME`, so every scenario creates `~/Documents/update-logs` on the real machine (ONEUP-0058) |
| §2.3 every `mktemp -d` is paired with its `rm -rf` | **nothing** — a scenario that drops the removal leaks its directory silently, and a count of the two cannot show it |
| §2.3 no network | **nothing automated, but the rule now holds.** Verified 2026-08-07 by running each suite inside an empty network namespace (`unshare -rn`): engine **246 passed / 0 failed** with T-1 SKIPping loudly, GUI **307 / 0** — identical to their networked results but for T-1. That is one measurement, not a gate: a *new* network call, or a window constructed above `gui-smoke.py`'s `_check_app_update` stub, would not be caught |
| §3 a mock fails loudly rather than quietly | several scenarios carry an `exit 99` trap. Nothing checks that a *new* mock has one |
| §4 one invariant, one test | nothing automatic |
| §5 the four correctness invariants | `tests/run-tests.sh` — this is what the suite is for, and the reason it exists |
| §6 poll for the condition, never sleep | **nothing** automatic |
| §7 a passing suite is silent | **nothing** — the GUI suite prints dozens of teardown tracebacks while passing (ONEUP-0062). §7 says how to count them and why the number is not stated |

**The §7 row names an open roadmap item instead of a gate**: it is a rule this suite breaks
every single run, which is why it is on the roadmap rather than in a footnote.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: §2.3's no-network rule was flatly false (the GUI suite makes 49 live GitHub requests per run, now ONEUP-0067), the traceback count was neither 28 nor fixed, its stated cause was backwards, and "both suites already do this correctly" was contradicted by a `sleep 0.5` and a silent SKIP branch in the suite itself (ONEUP-0068) |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | none | clean. |
| 4 | 2026-07-26 | 1 critical, 1 medium — **2 verified** | the What-checks-this table said the GUI suite does not redirect `HOME`. It does; the **engine** suite is the one that does not, and the row had borrowed the engine's roadmap id. Two rules, two failures, one row — and the table read as authoritative while saying the opposite of the truth. |
| 5 | 2026-07-26 | 2 medium — **0 verified, 2 dismissed** | both asked that §2.3's absolute *no test may reach the network* be softened to *should not*, because the section then names its own violations. That disclosure is deliberate, and the proposed wording is the uncheckable hedge `documentation.md` §8.1 bans. Dismissed explicitly rather than filtered. |
| 6 | 2026-07-26 | 1 medium — **1 verified** | converged (polish only). §3's parenthetical pointed at §2.1 for a claim §2.1 does not make, and blurred what the suite does assert about the keep-alive against what it does not. |
| 7 | 2026-09-28 | 2 lanes, cold, dispatched from outside the project; genre pinned standard; every lane held every question. Q1 5 · Q2 2 — 7 verified, 0 dismissed, all 7 fixed | **A pure audit (ONEUP-0107): no change armed it, so there is no armed-span share.** The four-question gate's first read of this document. **Both [Q2]s change what a test does**: §10's checklist said *all three* `ONEUP_*` paths (§2.3 said four, §3 three) against §2.1's *every override* — a direct-invocation scenario following it would have read the developer's real `hold.state` and `go.request`; and G4 said *one password prompt* where the design's G4 says it authenticates once, which is not the same as one dialog. [Q1]s: §2.1's block omitted `ONEUP_INHIBITED`, whose absence takes a real shutdown lock on the tester's session; §2.3's pairing check compared two totals that differ by two on a tree with no leak (`canary`, `hookd`), so it now states the pairing per variable — verified 110/110, 1/1, 1/1; the stub was named on `Updater`, where the window calls a module function, so a stub written from it would miss; `run_engine` and `setup_common` live in `tests/mock-env.sh`; `_query_auth_status` is in `auth.py`. Four of the seven surfaced while building the packet. **Fixed as exempt records, outside the tally:** §6's ONEUP-0068 paragraph and its What-checks row (the sleep became a poll), the six-traps count and the 56-constructions figure. All `v2`-only: `main` still has the sleep and keeps `run_engine` in `tests/run-tests.sh` |
| 8 | 2026-09-28 | 2 lanes, cold, briefed exactly as loop 7; every lane held every question. Q1 1 · Q3 1 — 2 verified, 1 dismissed, both fixed | **Both lanes led with the same pre-existing [Q1]**: the What-checks-this row said a real `sudo` is not on the mock `PATH`, so a scenario reaching for one gets the mock or nothing. `run_engine` prepends the mock directory and keeps the real `PATH` behind it, and `pkexec` is mocked nowhere — so a scenario without `setup_common`, an absolute path or `pkexec` reaches the real binary. The row now says half-covered and names what nothing catches. **The [Q3] was partly loop 7's own text**: *every override `run_engine` sets* reads as the `ONEUP_*` variables and drops the `PATH` prefix and `--log=`, and without `--log=` the engine defaults into the real `~/Documents/update-logs` (`update_system.sh`'s `if [[ -z "$LOG_FILE" ]]`). §2.1 and §10 now name both. **Dismissed:** a [Q2] setting §1's local-only differential harness against `workflow.md` §10's trap — `workflow.md` §6 itself names the harness as a deliberate exception, tracked by ONEUP-0195. Exempt records fixed alongside: the *75 of 76* count, and a claim that ONEUP-0062's headline says 56 (it carries no figure). Own-fix share of this loop: 1 of 2 |
| 9 | 2026-09-28 | 2 lanes, cold, briefed as loop 8 plus one carried source fact (`workflow.md` §6's differential row, which settled loop 8's dismissal); every lane held every question. Q2 1 · Q3 1 — 2 verified, 1 dismissed, both fixed. **Cap reached (3 for a standard)** | **A calm cap: findings ran 7 → 2 → 2, and the last loop's own-fix share was 1 of 2.** [Q3]: loop 7 rewrote the temp-directory pairing rule and nothing in the What-checks-this table said it goes unchecked — a row now does. [Q2], from a lane's open question: §2.2 bounded the GUI sandbox at `QApplication`, while `files-and-naming.md` §5.1 bounds it at import, and `oneup/gui/paths.py` computes `STATE_DIR`, `HISTORY` and `RUN_STATE` at import — a sandbox moved between the two would have written the user's real history. §2.2 and its row now name both bounds. **Dismissed:** that `run_engine` omits `ONEUP_AUTH_FILE` — only `--grant-auth`/`--revoke-auth` touch it, and those scenarios set it. No armed-span share: a pure audit. Nothing filed: the tail is empty |
