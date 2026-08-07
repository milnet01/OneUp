# ONEUP-0085 — Stop works while packages are downloading

**Status:** Draft
**Kind:** fix
**Roadmap:** ONEUP-0085
**Branch:** main (1.4.x — qualifies under `workflow.md` §1.1)
**Verified at:** `893bc43` — every claim naming a symbol below was resolved against this
tree, not recalled. Every measurement names the command that produced it.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** The system step downloads in one pass and installs in another, so the
long, network-bound, stall-prone half becomes interruptible — while the rpm transaction
itself stays exactly as uninterruptible as ONEUP-0047 requires.

## 1. Goal

When OneUp says *"the server may have stalled. Stopping now is safe"*, pressing **Stop**
ends the run within seconds, having installed nothing and kept every byte already
downloaded. After this item, that sentence is true in every phase in which it is shown.

## 2. Background

### 2.1 What happens today

`stop_pending` (`update_system.sh`) is consulted at exactly two kinds of place: in each
step's `if step_selected <key> && ! stop_pending` guard, and once more inside the system
step between `refresh_repos` and the transaction. The transaction itself is
`run_system_upgrade`, a single `zypper dup` (`zypper update` on Leap) whose output is piped
through `tee` into `progress_filter`.

The download therefore happens **inside** `run_system_upgrade`, past the last stop
boundary. A stop requested during it cannot be honoured until the whole step finishes.

### 2.2 The measured failure

A real run on the maintainer's machine, 2026-08-07, log
`~/.local/state/oneup/logs/2026-08-07_083514.log`:

```
Preloading: kernel-default-7.1.6-1.1.x86_64.rpm [end of response with 194225024 bytes missing]
Installation has completed with error.
@@STEP_END@@|system|fail|zypper reported an error
@@TIMING@@|system|296
```

The mirror stopped sending 194 MB into a 573 MB download. The GUI showed *"nothing received
for 1m 12s — the server may have stalled. Stopping now is safe."* — the liveness line from
`_tick_activity` in `updater.py`, gated on `STALL_SECONDS`. The user pressed Stop. Nothing
happened, because the run was inside `zypper dup`. The user then logged out and rebooted,
which is how ONEUP-0086 and ONEUP-0084 were found.

**The claim on screen is the defect this item removes.** `request_stop` writes
`STOP_REQUEST` and sets the button to *"Stopping…"*; during the transaction that promise
cannot be kept.

### 2.3 Why the download is safe to interrupt and the install is not

ONEUP-0047 forbids signalling the engine because a `SIGTERM` mid-`zypper dup` either leaves
rpm half-applied or orphans a zypper that carries on. **Both harms belong to the rpm
transaction.** During a download pass no transaction has started: zypper is fetching files
into `/var/cache/zypp/packages`.

Measured rather than assumed, 2026-08-07, on zypper 1.14.98:

| Question | Command | Result |
| --- | --- | --- |
| Does `dup` accept download-only? | `zypper dup --help \| grep download-only` | `-d, --download-only  Only download the packages, do not install.` |
| Does SIGTERM end it? | `setsid zypper …dup --download-only &` then `kill -TERM -- -$!` | No zypper process remained |
| Is the lock released? | `cat /run/zypp.pid` before and after | Held `47595`; empty afterwards |
| Is the next run blocked? | `zypper --no-refresh dup --dry-run` afterwards | Computed `75 packages to upgrade` — no stale lock |
| Are partial files left? | `find /var/cache/zypp/packages -name '*.rpm.part*'` | None |
| Is fetched work kept? | `du -sh /var/cache/zypp/packages` | `217M` retained |

The last row is what makes stopping *free* rather than merely possible: an interrupted
download loses nothing, so the retry resumes rather than restarting. ONEUP-0087 is its
partner — it stops the cache step discarding those bytes after a failed system step.

## 3. Scope decisions

- **The install pass is never signalled.** ONEUP-0047 stands unamended. The only thing this
  item makes interruptible is the download.
- **Two passes, one step.** The user sees one *Updating system packages* row with one
  outcome. Splitting the marker stream would break the GUI's step model
  (`marker-protocol.md` §3) for a change that is internal.
- **Poll in the foreground; spawn no watcher.** The engine's existing precedent — the sudo
  keep-alive in `sudo_init` — needs `setsid` and a process-group kill precisely because it
  is a spawned helper that could outlive the run (§2.4 of `security.md`). This item needs no
  helper: the download runs as a background job of the engine and the engine's own
  foreground loop polls. Nothing is spawned, so nothing can be orphaned.
- **Leap keeps parity.** `run_system_upgrade` branches on `/etc/os-release` for
  `update` vs `dup`; both accept `--download-only`, so both are split.
- **Stop resolution is a poll interval, not instant.** A file-watch would be tighter and
  needs `inotify`; the existing stop mechanism is a file whose mtime is compared, and a
  short poll matches it with no new dependency.

## 4. Design

### 4.1 The split

`run_system_upgrade` becomes two functions over one shared argv, so the two passes cannot
drift apart:

- `system_txn_argv` — builds the `zypper` argument list once (Leap `update` vs Tumbleweed
  `dup --allow-vendor-change`), and is the single place either is stated.

  **It serves three callers, not two.** The `--size=<step>` probe already runs the same
  transaction with `--dry-run` to compute the download figure, and today it carries its own
  copy of the distro branch and the flags:

  ```
  $ grep -n 'allow-vendor-change' update_system.sh | grep -v ':\s*#'
  495:            --allow-vendor-change --dry-run
  1193:        sudo env LC_ALL=C zypper --non-interactive dup --allow-vendor-change 2>&1 \
  ```

  A flag added to one and not the other makes the size OneUp *quotes* describe a different
  transaction from the one it *runs* — the class of defect ONEUP-0035 already cost this
  project once, where the figure shown and the work done disagreed. Folding the probe onto
  the same argv is therefore part of this item rather than adjacent tidying, and INV-5 is
  what holds it.
- `run_system_download` — that argv plus `--download-only`, run as a background job with
  the engine polling for a stop.
- `run_system_commit` — the same argv with no `--download-only`. Every package is already
  cached, so this pass performs no network I/O and is the only pass that touches rpm.

`run_system_upgrade` remains as the caller of both, keeping its current contract: it sets
the global `ok` and writes the transaction output to `$SYS_LOG`. Its existing callers —
the first call in the system step and the `--auto-skip-repos` retry after
`find_failing_repos` — are unchanged.

### 4.2 The stop boundary

Three boundaries exist after this item, where two do today:

1. Before `refresh_repos` — unchanged.
2. After `refresh_repos`, before the transaction — unchanged.
3. **New:** after the download pass, before the commit pass.

Boundary 3 is reached both when the download completes normally and when it is interrupted.
In either case, if `stop_pending` is true the step ends `skip` with
`"stopped before installing anything"` — the wording boundary 2 already uses, because the
user-visible fact is identical.

### 4.3 Interrupting the download

The download runs as a background job so the engine keeps a foreground loop:

- The job is started **without** command substitution. `security.md` §2.2 forbids a
  privileged call inside `$(…)` because sudo's tty-less credential is keyed to the parent
  pid; a background job's parent is still this shell, exactly as a pipeline element's is,
  which is why `run_system_upgrade`'s comment says sudo must stay the pipeline's first
  element. The same reasoning admits `&`, and this is the assumption the implementation
  must confirm first (§7, T-1).
- The loop polls `stop_pending` every `STOP_POLL_SECONDS`, exits when the job does, and on
  a stop sends `SIGTERM` to the download's **process group**, so zypper's curl children go
  with it rather than being reparented.
- `STOP_POLL_SECONDS` is overridable by environment, matching `ONEUP_REFRESH_TIMEOUT`, so
  the suite need not wait out a real interval.

A stop seen here sets a flag distinguishing *interrupted* from *failed*, so §4.4 does not
report a stop as an error.

### 4.4 Outcome mapping

| What happened | Step outcome | Why |
| --- | --- | --- |
| Download ok, commit ok | `ok` | unchanged from today |
| Download ok, stop pending at boundary 3 | `skip` — `stopped before installing anything` | nothing installed |
| Download interrupted by a stop | `skip` — `stopped before installing anything` | nothing installed; bytes kept |
| Download failed (mirror, disk, signature) | `fail` | as today, but the hint can now say the *download* failed |
| Commit failed | `fail` | as today |

A stop must not increment `ERRORS`, or `@@DONE@@` reports `errors` for a run the user chose
to end — the failure ONEUP-0074 exists to prevent.

### 4.5 Progress continuity

`progress_filter` reads zypper's own wording and emits `@@PROGRESS@@|system|<n>|…`. Both
passes pipe through it. The download pass emits the `download` phase; the commit pass emits
`install`. Because the commit pass finds everything cached, its own preload lines are
`[already in cache]` and pass through as they do today. The GUI's `_progress_phase` already
distinguishes the two phases, so no marker or parser change is required.

## 5. Correctness invariants

The suite is `tests/run-tests.sh` throughout — every clause below is engine behaviour.

- **INV-1** A stop requested while packages are downloading ends the run without installing
  anything.
  *Test:* a mock `zypper` whose `--download-only` invocation sleeps long enough to be
  interrupted, and whose commit invocation writes a sentinel file. The scenario touches
  `$ONEUP_STOP_FILE` after the download starts, then asserts `@@STEP_END@@|system|skip`,
  and asserts **the sentinel does not exist**. Breaks on today's engine, where there is no
  download pass to interrupt and the commit always runs. The sentinel is what makes this
  test the invariant rather than a restatement of INV-2: asserting only on the marker would
  pass against an engine that emitted `skip` and installed anyway.

- **INV-2** The commit pass is never signalled, whatever the stop file says.
  *Test:* a mock `zypper` whose commit invocation records every signal it receives to a file
  and then exits 0. The scenario creates the stop request *after* the commit has begun and
  asserts the recorded signal list is empty and the step still ends `ok`. Breaks if a later
  change extends the download poll across both passes — the single most plausible
  regression, and the one ONEUP-0047 forbids.

- **INV-3** A stopped download leaves no process behind.
  *Test:* the scenario records `pgrep` output before the run and after it, and asserts no
  new process survives — the shape the existing keep-alive orphan test already uses. Breaks
  if the download is spawned into its own session and the group signal misses it, which is
  precisely how the keep-alive leak in ONEUP-0003 happened.

- **INV-4** A stopped run is not reported as a failed one.
  *Test:* the INV-1 scenario also asserts `@@DONE@@|stopped` and `check_absent`
  `@@DONE@@|errors`. Breaks if the interrupted download's non-zero exit is folded into `ok`,
  which is the natural way to write it and is wrong.

- **INV-5** The download pass, the commit pass and the `--size` probe state the transaction
  command in exactly one place.
  *Test:* `grep 'allow-vendor-change' update_system.sh | grep -vc '^\s*#'` returns 1.
  → today it returns **2** (the probe at §4.1 and the transaction), so the clause
  discriminates; the comment filter is required because a third match is prose. Breaks the
  moment someone adds a flag to one caller and not another — a divergence that would
  download one set of packages, install a second and quote the size of a third, and which
  no behavioural test would catch because all three would still succeed.

- **INV-6** The user sees one step, not two.
  *Test:* a successful run asserts exactly one `@@STEP_BEGIN@@|system` and one
  `@@STEP_END@@|system` — `grep -c`, compared to 1. Breaks if the split is implemented by
  calling `begin_step`/`end_step` per pass, which would make the GUI draw two rows and
  mis-count "step 1 of 5".

- **INV-7** A privileged call in either pass keeps this shell as its parent.
  *Test:* the sudo-sentinel already in the suite — a mock `sudo` that records its
  parent pid — asserts both passes record the engine's own pid, so neither sits inside a
  command substitution. Breaks on `out=$(sudo …)`, which is the shape that caused the
  double password prompt this project keeps re-learning (`security.md` §2.2).

## 6. Failure modes

| Situation | Behaviour |
| --- | --- |
| `--download-only` unsupported (an older or forked zypper) | The download pass fails with a usage error and the step fails, having installed nothing. Recovery is a hint naming the flag. §7 T-2 pins that a usage failure is not mistaken for a mirror failure. |
| Download interrupted, user retries | The cache still holds what was fetched (§2.3), so the retry resumes. Requires ONEUP-0087, which is why the two ship together. |
| Stop arrives in the window between the download ending and the commit starting | Boundary 3 catches it; this is the normal path, not an edge. |
| Stop arrives during the commit | Ignored until the step ends (INV-2). The GUI's liveness line must not claim otherwise — §8. |
| SIGTERM does not end zypper | The poll loop stops signalling after the job exits; if it never exits, the run behaves as today. Deliberately no `SIGKILL` escalation: a `SIGKILL`ed zypper is the abandoned-lock case, and waiting is strictly safer than that. |
| Disk fills during the download | zypper fails the download pass; nothing is installed. Better than today, where the same failure can occur part-way through a commit. |

## 7. Tests

§5 owns the invariant clauses. Two further scenarios exist for facts the invariants assume:

- **T-1 — the background-job credential assumption.** Before implementing §4.3, confirm that
  `sudo cmd &` reuses the warm credential as `sudo cmd | …` does. The claim in §4.3 is
  reasoning from `run_system_upgrade`'s comment, not a measurement, and it is the one
  assumption in this spec that has not been run. If it is false, §9's third alternative
  (keep the pipeline in the foreground, poll from a `SIGCHLD`-free subshell) becomes the
  design. **This test gates the implementation, not the spec.**
- **T-2 — a usage failure is not a mirror failure.** A mock zypper rejecting
  `--download-only` must produce a hint naming the flag, not the "check your internet
  connection" hint `repo_scoped_failure` would otherwise reach for.

The suite's mock `zypper` already dispatches on `"$*"`, so both passes are distinguishable
by matching `*download-only*` before the general `*dup*` case — order matters, and the
existing scenarios put the narrower pattern first for the same reason.

## 8. Docs & release

- **`docs/reference/marker-protocol.md`** — no marker changes (§4.5). Its §3 step model
  gains a sentence that the system step now runs two zypper passes behind one
  `STEP_BEGIN`/`STEP_END` pair, so a future reader does not treat the second `download`
  phase as a protocol violation.
- **`CLAUDE.md` §6** — the *"Never signal the engine to stop a transaction"* trap is
  **sharpened, not withdrawn**: the transaction is still never signalled; the download
  pass now is. Left as-is it reads as forbidding this item.
- **`docs/standards/security.md` §6** — same sharpening, in the document that owns the
  rule. §6 is the home; `CLAUDE.md` gets the pointer.
- **`updater.py`** — the liveness line's *"Stopping now is safe"* is the sentence this item
  makes true. It stays, and no wording change is needed once the engine honours it.
- **`CHANGELOG.md`** — under **Fixed**, with ONEUP-0086 and ONEUP-0087, as 1.4.1.

## 9. Alternatives considered (and rejected)

- **Leave the download uninterruptible and correct the GUI's wording instead.** Cheapest,
  and it removes the false promise. Rejected because the user's problem is not that the
  message lied — it is that a stalled mirror holds the machine with no way out, and the
  reboot that follows is what damages it (ONEUP-0086). Honest wording for a trap is still a
  trap.
- **A per-download stall timeout, as `refresh_repos` uses for metadata.** Bounds the hang
  without any signalling design. Rejected as insufficient rather than wrong: it fires on a
  timer the user cannot influence, so Stop still does nothing, and picking a threshold that
  never aborts a merely-slow mirror means picking one far longer than a user will wait. It
  remains a reasonable *addition* later.
- **Poll from a spawned watcher rather than the engine's foreground.** Rejected under
  `security.md` §2.4: a helper that signals must itself be watched, and the keep-alive
  already demonstrates the cost of getting that wrong. Kept as the fallback if T-1 fails.
- **`zypper --xmlout` for the whole transaction.** Would remove the prose parsing that
  ONEUP-0035 and ONEUP-0046 both punished. Out of scope here and genuinely attractive —
  filed as part of ONEUP-0091.

## 10. Out of scope

- Making the Flatpak, firmware, orphans or cache steps interruptible mid-tool. They are
  short, and none has produced a stall report.
- Any change to how the GUI requests a stop. `request_stop` and `STOP_REQUEST` are
  unchanged; this item only changes where the engine listens.
- Resuming a partially-downloaded package. zypper's own caching already does this (§2.3).
- The reboot/logout hang (ONEUP-0086) and the discarded cache (ONEUP-0087) — siblings that
  ship alongside, specified in their own bullets.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
