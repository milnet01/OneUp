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

`stop_pending` (`update_system.sh`) is consulted at three kinds of place: in each step's
`if step_selected <key> && ! stop_pending` guard; **inside `refresh_repos`, between
repositories** (`stop_pending && return 0`); and once more inside the system step between
`refresh_repos` and the transaction. The transaction itself is `run_system_upgrade`, a
single `zypper dup` (`zypper update` on Leap) whose output is piped through `tee` into
`progress_filter`.

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

The transfer ended **194 MB short** — `bytes missing`, not bytes received. The GUI showed
*"nothing received for 1m 12s — the server may have stalled. Stopping now is safe."* — the
liveness line from `_tick_activity` in `updater.py`, gated on `STALL_SECONDS`. The user
pressed Stop. Nothing happened, because the run was inside `zypper dup`. The user then
logged out and rebooted, which is how ONEUP-0086 and ONEUP-0084 were found.

**What this item does NOT claim: that the download failure has been diagnosed.** It
reproduced four times on 2026-08-07 and two hypotheses were tested and falsified —
mirror striping (`ZYPP_MULTICURL=0`: failed identically) and libzypp's 180-second
`download.transfer_timeout` (raised to 3600: failed identically, 180 MB short). What is
established is only the shape: a large package repeatedly truncates and its fallback mirror
404s, while the same URL serves `HTTP/1.1 200` with `content-length: 210194084` and a
range request pulls 5 MB at 448 KB/s.

That gap is the whole argument for this item, and it is stronger than a diagnosis would be.
**OneUp cannot fix openSUSE's download layer, and does not need to.** What it owes the user
when a download will not complete — for any reason, diagnosed or not — is the ability to
stop waiting. Today it offers a button that does nothing. The underlying failure is filed
separately as ONEUP-0094; this item is deliberately independent of its outcome.

**The claim on screen is the defect this item removes.** `request_stop` writes
`STOP_REQUEST` and sets the button to *"Stopping…"*; during the transaction that promise
cannot be kept.

### 2.3 Why the download is safe to interrupt and the install is not

ONEUP-0047 forbids signalling the engine because a `SIGTERM` mid-`zypper dup` either leaves
rpm half-applied or orphans a zypper that carries on. **Both harms belong to the rpm
transaction.** During a download pass no transaction has started: zypper is fetching files
into `/var/cache/zypp/packages`.

Measured rather than assumed, 2026-08-07, on zypper 1.14.98:

All commands below were run as root (`sudo …`), which these operations require; the `sudo`
is omitted from the table only to keep the column readable.

| Question | Command | Result |
| --- | --- | --- |
| Does `dup` accept download-only? | `zypper dup --help \| grep -i download.only` | `-d, --download-only  Only download the packages, do not install.` |
| Does `update` (the Leap verb) accept it? | `zypper update --help \| grep -i download.only` | identical line — so **both** distro branches split |
| Does SIGTERM end it? | `setsid zypper …dup --download-only &` then `kill -TERM -- -$!` | No zypper process remained |
| Is the lock released? | `cat /run/zypp.pid` before and after | Held `47595`; empty afterwards |
| Is the next run blocked? | `zypper --no-refresh dup --dry-run` afterwards | Computed `75 packages to upgrade` — no stale lock |
| Are partial files left? | `find /var/cache/zypp/packages -name '*.rpm.part*'` | None |
| Is fetched work kept? | `du -sh /var/cache/zypp/packages` | `217M` retained |

**The SIGTERM row proves less than it appears to, and the gap is closed elsewhere.** It
signalled a *bare* `zypper` from a *root* shell, so it establishes that zypper survives the
signal cleanly — but not that the engine can deliver it, since the engine is unprivileged
and the real zypper runs under `sudo`. §4.3 is where that half is settled, and it is settled
by a different measurement.

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
  `update` vs `dup`; both accept `--download-only` (measured, §2.3), so both are split.
- **Stop resolution is a poll interval, not instant.** A file-watch would be tighter and
  needs `inotify`; the existing stop mechanism is a file whose mtime is compared, and a
  short poll matches it with no new dependency.

- **The user is assumed to have no terminal and no expertise. This is a constraint on the
  design, not a note about the audience.** Diagnosing the 2026-08-07 failure took
  `ZYPP_MULTICURL=0`, a `download.transfer_timeout` override via a `zypp.conf.d` drop-in, a
  `curl -r` range probe, reading `/run/zypp.pid`, and a hand-delivered `SIGTERM` to a
  root-owned process — and **two of those hypotheses were wrong anyway**. None of it is
  available to someone who installed OneUp to avoid the command line, which is the entire
  reason OneUp exists (`README.md`).

  So an outcome an ordinary user cannot act on is not an acceptable outcome. Concretely,
  three things follow and each is testable: a failure the user cannot fix must still be
  **stoppable** (this item); it must leave the machine **no worse** and the download
  **not discarded** (ONEUP-0087, shipped); and where a recovery exists that a knowledgeable
  user would apply, the app should apply it rather than describe it (ONEUP-0094). "Tell the
  user to run a command" is the failure mode this bullet forbids.

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

**`$SYS_LOG` is written by both passes, and the second must append.** `tee "$SYS_LOG"`
truncates, so a commit pass using the same redirection would erase the download pass's
output. Three consumers read that file after the step — the `Nothing to do.` /
`N packages to upgrade` change detection, `reboot_reason_from_log`, and the failure-hint
`grep`s — and the download half is where a download failure's evidence lives. So the
download pass uses `tee "$SYS_LOG"` (truncating, as today, since it runs first) and the
commit pass uses `tee -a "$SYS_LOG"`.

### 4.2 The stop boundary

Four boundaries exist after this item, where three do today:

1. Before `refresh_repos` — unchanged.
2. Between repositories inside `refresh_repos` — unchanged.
3. After `refresh_repos`, before the transaction — unchanged.
4. **New:** after the download pass, before the commit pass — plus, uniquely, the ability
   to land *during* the pass that precedes it (§4.3). Every existing boundary is a gap
   between operations; this is the first that interrupts one.

Boundary 3 is reached both when the download completes normally and when it is interrupted.
In either case, if `stop_pending` is true the step ends `skip` with
`"stopped before installing anything"` — the wording boundary 2 already uses, because the
user-visible fact is identical.

### 4.3 Interrupting the download

**The engine does not signal anything. A root-side wrapper owns the download and signals
its own child.** The pipeline stays in the foreground, in exactly the shape
`run_system_upgrade` uses today:

```bash
sudo env LC_ALL=C bash -c '<wrapper>' _ "$STOP_FILE" "$RUN_STATE_FILE" "$STOP_POLL_SECONDS" \
    2>&1 | tee "$SYS_LOG" | progress_filter system download
```

The wrapper starts zypper, polls for the stop request, `SIGTERM`s zypper when it sees one,
then `wait`s and exits with zypper's status.

**Three measured facts forced this shape, and the obvious design fails all three.** The
first draft backgrounded the pipeline and had the engine signal a process group. Measured
2026-08-07 on this machine's bash:

| Question | Command | Result |
| --- | --- | --- |
| Does a background pipeline get its own process group? | `sleep 30 \| cat &` then compare `ps -o pgid=` | **No** — job pgid `56117` = engine pgid `56117` |
| What does `$!` identify? | `sleep 9 \| head -c0 &` then `ps -o comm= -p $!` | the pipeline's **last** element, not zypper |
| Does backgrounding change sudo's parent? | `sh -c 'echo $PPID' \| cat &` | **No** — ppid is still the engine |

So `kill -TERM -- -$pgid` from the engine would have signalled **the engine itself**, which
`security.md` §6.3 forbids outright; `kill $!` would have signalled `progress_filter`; and
the engine runs unprivileged while zypper runs as root, so a direct `kill` earns `EPERM`
regardless. Only the third row came out in the design's favour — and it is the one the
first draft bothered to argue, which is why the other two are tabulated here rather than
reasoned about again.

Inside the wrapper all three problems vanish: it is already root, so signalling its own
child needs no privilege; it holds zypper's pid directly, so no process group is involved;
and because the pipeline is in the **foreground**, `${PIPESTATUS[0]}` still carries
zypper's status exactly as today (§4.4 depends on this entirely).

**Verified end to end before this section was written** — a stop file created 3 s into a
run produced `[root] stop seen -> SIGTERM`, `child rc=143`, and `PIPESTATUS[0] = 143` in
the engine. 143 is `128 + SIGTERM`, which is how §4.4 tells an interrupted download from a
failed one; it needs no separate flag.

- **`STOP_POLL_SECONDS="${ONEUP_STOP_POLL_SECONDS:-2}"`**, in the engine's existing idiom
  (`REFRESH_TIMEOUT="${ONEUP_REFRESH_TIMEOUT:-120}"`). §1's "within seconds" means this
  interval plus zypper's own exit, and the suite overrides it rather than waiting one out.
- The wrapper re-implements `stop_pending`'s staleness rule — a request older than
  `run.state` is a leftover (`security.md` §6.2) — because it cannot call an engine
  function across `sudo bash -c`. That duplication is deliberate and is why both paths take
  the two file paths as arguments rather than reading globals.
- **Nothing outlives the engine.** The wrapper is `sudo`'s child, `sudo` is the foreground
  pipeline's first element, and the engine `wait`s on the pipeline — the same lifetime the
  transaction has today. This is not the `security.md` §2.4 case: no helper is detached, so
  there is no pid to watch.

### 4.4 Outcome mapping

The download pass's `${PIPESTATUS[0]}` is the discriminator: **143** (`128 + SIGTERM`) is
an interrupted download, anything else non-zero is a failed one.

| What happened | `ok` | Step outcome | Repo probe + `--auto-skip-repos` retry |
| --- | --- | --- | --- |
| Download ok, commit ok | true | `ok` | not reached |
| Download ok, stop pending at boundary 3 | true | `skip` — `stopped before installing anything` | **skipped** |
| Download interrupted (rc 143) | true | `skip` — `stopped before installing anything` | **skipped** |
| Download failed (rc ≠ 0, ≠ 143) | false | `fail` | runs, as today |
| Commit failed | false | `fail` | runs, as today |

**The `ok` column is load-bearing and is the reason this table gained it.** `ok=false`
is what admits the system step to `repo_scoped_failure` → `find_failing_repos` →
a second `run_system_upgrade` under `--auto-skip-repos`. If an interrupted download set
`ok=false`, pressing Stop would **restart the transaction the user just stopped** — a
worse outcome than the bug this item fixes. So rc 143 sets `ok=true` and short-circuits
before the probe.

A stop must also not increment `ERRORS`, or `@@DONE@@` reports `errors` for a run the user
chose to end (`end_step … skip` already avoids this; the row above is what keeps it true).

### 4.5 Progress continuity

`progress_filter` reads zypper's own wording and emits `@@PROGRESS@@|system|<n>|…`. Both
passes pipe through it, and **it needs a second argument to stay correct**, which the first
draft denied.

Its `Preloading:*)` and `Retrieving:*)` cases emit the `download` phase **unconditionally**
— the function has no idea which pass invoked it. Since the commit pass re-reads every
cached package and prints `Preloading: … [already in cache]` for each, it would re-emit
`download`-phase markers *after* the download finished, flipping the GUI's
`_progress_phase` back and resetting its byte total (`want` is a per-invocation local, so
the commit pass emits `…|download|0|0`). The user would watch the progress display restart
from zero at the exact moment the install began.

So `progress_filter` takes the pass as a parameter — `progress_filter system download` and
`progress_filter system install` — and the `Preloading:`/`Retrieving:` cases emit that
phase rather than a hard-coded one. **No marker changes**: the field already exists in the
protocol and the GUI already distinguishes the two values. What changes is one function
signature and its two call sites.

`PROGRESS_SEEN_FILE` is written with a truncating `>` at the end of each invocation, so the
commit pass would erase the download pass's count and trip the ONEUP-0046 stale-parser
canary on a healthy run. The **download** pass owns that file; the commit pass does not
write it.

## 5. Correctness invariants

The suite is `tests/run-tests.sh` throughout. All but one clause below assert engine
*behaviour*; **INV-5 is a structural check over the source** and is called out as such
where it appears, because a reader who takes the preamble literally will look for a
behavioural test that cannot exist.

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
  *Test:* a mock `zypper` whose commit invocation traps and records every signal it
  receives, touches a `commit-started` sentinel, then sleeps briefly and exits 0. The
  scenario **waits for that sentinel** before creating the stop request, then asserts the
  recorded signal list is empty and the step still ends `ok`. The barrier is the whole
  test: without it the scenario races the mock's start-up and can write the stop file
  before the commit exists, which passes while exercising nothing. Breaks if a later change
  extends the download poll across both passes — the single most plausible regression, and
  the one ONEUP-0047 forbids.

- **INV-3** A stopped download leaves no process behind — neither zypper nor the wrapper.
  *Test:* the scenario records `pgrep` output before the run and after it, and asserts no
  new process survives — the shape the existing keep-alive orphan test already uses. Breaks
  if the wrapper `SIGTERM`s zypper and exits without `wait`ing, leaving a root-owned child
  reparented to init: the same leak shape as ONEUP-0041, where two keep-alives were found
  still running 40 minutes after the runs that spawned them had been killed
  (`security.md` §2.4).

- **INV-4** A stopped run is not reported as a failed one.
  *Test:* the INV-1 scenario also asserts `@@DONE@@|stopped` and `check_absent`
  `@@DONE@@|errors`. Breaks if the interrupted download's non-zero exit is folded into `ok`,
  which is the natural way to write it and is wrong.

- **INV-5** The download pass, the commit pass and the `--size` probe state the transaction
  command in exactly one place — **on both distros**.
  *Test:* `grep -cE '^\s*system_txn_argv' update_system.sh` returns **4** — one definition
  plus the three callers (download pass, commit pass, `--size` probe).
  → before the change it returned **0**; after it returns **4**. The `^\s*` anchor is
  required: a bare `grep -c` returns 5, because the `SYS_TXN` declaration's trailing
  comment names the function.
  **Three earlier drafts of this clause were wrong, and every one failed when run** —
  which is the argument for the two-run rule, not an aside. The first asserted
  `grep -c 'allow-vendor-change' … == 1`; that is Tumbleweed-only, so a probe keeping its
  own `zypper update` branch would score clean while the Leap paths diverged. The second
  widened the pattern to both verbs and predicted 4; it returns **3**, because the
  Tumbleweed probe wraps across two lines (`… dup \` / `--allow-vendor-change --dry-run`)
  and a line-based grep cannot see it. Counting the callers avoids both traps: it does not
  care how the argv is spelled or wrapped. Breaks the moment someone adds a flag to one
  caller and not another, which would download one set of packages, install a second and
  quote the size of a third — and which no behavioural test would catch, because all three
  would still succeed.

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
| `--download-only` unsupported (an older or forked zypper) | **The engine falls back to today's single un-split pass for the rest of the run**, emits a HINT saying Stop will only work between steps, and completes the update normally. Turning a working update into a total failure over a missing convenience would be a worse bug than the one this item fixes. No minimum zypper version is imposed, because the fallback makes one unnecessary. §7 T-2 pins the fallback and that the usage failure is not mistaken for a mirror failure. |
| Download interrupted, user retries | The cache still holds what was fetched (§2.3), so the retry resumes. Requires ONEUP-0087, which is why the two ship together. |
| Stop arrives in the window between the download ending and the commit starting | Boundary 3 catches it; this is the normal path, not an edge. |
| Stop arrives during the commit | Ignored until the step ends (INV-2) — by design, and permanently. The GUI still says "Stopping now is safe" in this phase, which stays wrong after this item; **ONEUP-0095** closes it by disabling the control rather than rewording the sentence, and §8 records why that is not folded in here. |
| SIGTERM does not end zypper | The poll loop stops signalling after the job exits; if it never exits, the run behaves as today. Deliberately no `SIGKILL` escalation: a `SIGKILL`ed zypper is the abandoned-lock case, and waiting is strictly safer than that. |
| Disk fills during the download | zypper fails the download pass; nothing is installed. Better than today, where the same failure can occur part-way through a commit. |

## 7. Tests

§5 owns the invariant clauses. Two further scenarios exist for facts the invariants assume:

- **T-1 — one password prompt, not two.** The wrapper adds a `bash -c` between `sudo` and
  zypper, and `security.md` §2.2 is the rule this project has re-learned most often. A
  scenario counts the mock `sudo`'s interactive validations across a full run and asserts
  the split did not add one. This replaces a draft T-1 that proposed measuring whether
  `sudo cmd &` keeps its parent — a question §4.3 no longer asks, because the pipeline is
  no longer backgrounded. (The measurement was run anyway: it does keep its parent. The
  design changed for the *other* two reasons, not that one.)
- **T-2 — an unsupported flag degrades, it does not fail.** A mock zypper that rejects
  `--download-only` with a usage error must leave the run **succeeding** via the §6
  fallback, emit the HINT naming the flag, and not reach the "check your internet
  connection" hint `repo_scoped_failure` would otherwise produce.

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
- **`updater.py`** — the liveness line's *"Stopping now is safe"* becomes true **in the
  download phase only**, and this item does not make it true in the commit phase, where
  INV-2 guarantees the opposite. `_tick_activity` appends that clause whenever `stalled`,
  with no reference to `_progress_phase`, so after this item the sentence is right when the
  bar says *Downloading* and still wrong when it says *Installing*.

  **This item does not fix that, and says so rather than implying otherwise.** The honest
  fix is to gate the *control* rather than reword the sentence — Stop disabled during the
  commit, with a tooltip — which is **ONEUP-0095**, sequenced after this one because until
  the download pass exists there is no phase in which Stop works at all. §1's promise is
  therefore scoped to the download phase, and §6's row for a stop during the commit records
  the residual gap as belonging to 0095.
- **`CHANGELOG.md`** — under **Fixed**, with ONEUP-0086 and ONEUP-0087, as 1.4.1.

- **`docs/specs/ONEUP-0054-python-engine.md`** — **§5 of this document binds the Python
  engine, not just the Bash one.** 2.0 replaces `update_system.sh` outright, so §4.3's
  mechanism — a `sudo bash -c` wrapper, `${PIPESTATUS[0]}`, a shell poll loop — does **not**
  port and should not be transcribed. The seven invariants do, unchanged, because every one
  is stated as observable behaviour rather than as shell: a Python engine still owes a stop
  that lands during the download (INV-1), a commit that is never signalled (INV-2), no
  orphan (INV-3), a stop that is not an error (INV-4), one argv (INV-5), one step (INV-6),
  and one authentication (INV-7).

  Recorded because the natural failure is silent: 2.0 rewrites the file this item edits, and
  a rewrite that satisfies its own spec while quietly dropping a 1.4.x fix regresses a
  shipped bug with nothing to catch it. Verified 2026-08-07 that this is presently a
  documentation obligation only — `v2` is a strict ancestor of `main` with no commits of its
  own, so today's fixes reach it by fast-forward rather than by porting. That stops being
  true the moment 2.0 work begins, which is why the obligation is written down now.

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
- **Poll from a detached watcher process rather than inside the privileged wrapper.**
  Rejected under `security.md` §2.4 and **not kept as a fallback** — an earlier draft named
  it as one while also rejecting it, which left an implementer two incompatible
  instructions. A helper that signals must itself be watched, and ONEUP-0041 is what that
  costs when it goes wrong. §4.3's wrapper needs no watcher because it *is* the parent of
  the thing it signals.
- **Background the pipeline and signal from the engine.** This was the first draft of
  §4.3 and it is recorded because it is the design a reader will reach for. It fails three
  ways, all measured in §4.3: the job stays in the engine's own process group, so the group
  kill hits the engine; `$!` names the pipeline's last element rather than zypper; and the
  unprivileged engine cannot signal a root process anyway. It also destroys `PIPESTATUS`,
  which §4.4 depends on entirely.
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
| 1 | 2026-08-07 | 2 lanes; 5 critical, 6 high, 5 medium, 5 low — **20 verified, 1 dismissed** — 20 draft defects vs 0 fix collateral (all fixed). Dimensions: dim 5×6, dim 2×5, dim 7×2, dim 15×2, dim 6×2, dim 4×1, dim 8×1, dim 9×1, dim 10×1 | **The whole of §4.3 was wrong, and both lanes led with it.** The draft backgrounded the transaction pipeline and had the engine signal the job's process group. Measured during verification: a background pipeline in a non-interactive script gets **no process group of its own** (job pgid `56117` = engine pgid `56117`), so the prescribed `kill -TERM -- -$pgid` would have signalled **the engine itself** — which `security.md` §6.3 forbids in as many words. `$!` names the pipeline's **last** element (`progress_filter`), not zypper. And the engine is unprivileged while zypper runs as root, so a direct kill earns `EPERM` regardless. Backgrounding also destroys `PIPESTATUS`, and `progress_filter` ends in an unconditional `return 0` — so **every download would have reported success**, collapsing four rows of §4.4 into one. An implementer following the draft would have shipped a bug strictly worse than the one this item fixes. §4.3 is rebuilt around a root-side wrapper that owns and signals its own child inside a **foreground** pipeline: sudo stays the first element (the shape §2.2 requires), the signal needs no privilege, no process group is involved, and `${PIPESTATUS[0]}` survives — verified end to end before the section was rewritten (`stop seen -> SIGTERM`, `child rc=143`, `PIPESTATUS[0]=143`). **One lane claim was dismissed on measurement**: both lanes asserted that backgrounding reparents sudo under an intermediate subshell, breaking the tty-less credential; it does not — child ppid stayed the engine's in all three shapes tested. The design changed for the other two reasons, and the dismissal is recorded because the draft's one *defended* assumption turned out to be its only correct one. **The most consequential finding neither lane led with was §4.4's missing `ok` column**: an interrupted download setting `ok=false` admits the step to `repo_scoped_failure` → `--auto-skip-repos`, so pressing Stop would have **restarted the transaction the user just stopped**. **Three draft defects died during context-packet construction**, before a lane was spent — two `sed` windows landed on the wrong code and the security.md extraction returned nothing, each caught by checking that every packet window was non-empty. **INV-5's clause was wrong twice and both were caught by running it**: `allow-vendor-change` alone is Tumbleweed-only (a Leap probe would score clean while diverging), and the widened pattern predicted 4 but returns 3, because the Tumbleweed probe wraps across two lines where a line-based grep cannot see it. It is structural now (`grep -c 'system_txn_argv'`, 0 today → 4 after). Also corrected: the boundary census omitted `refresh_repos`' own between-repository check (three today, not two); INV-3 cited ONEUP-0003 for the keep-alive leak, which is **ONEUP-0041**; `progress_filter` emits the `download` phase unconditionally, so the commit pass would have reset the GUI's progress to zero at the moment installing began; `$SYS_LOG`'s `tee` truncates, so the second pass would have erased the first's evidence; and §2.2 read `194225024 bytes missing` as bytes *received*. **§6 and §8 flatly contradicted each other** on whether `updater.py` changes — settled by gating the control rather than rewording the sentence, filed as **ONEUP-0095** at the user's request during the loop. **Two of the author's own hypotheses about the motivating failure were falsified mid-loop** (mirror striping, then libzypp's 180 s `download.transfer_timeout` — both reproduced the failure unchanged), so §2.2 now states the shape of the failure and explicitly declines to claim a diagnosis; the item is deliberately independent of ONEUP-0094's outcome. The document left this loop at 465 lines, up from 316. |
