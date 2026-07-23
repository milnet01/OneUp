# ONEUP-0025 — Survive a single broken software source instead of failing the whole update

**Status:** Draft → cold-eyes pending
**Roadmap:** ONEUP-0025 (🚧)
**Kind:** feature (engine + GUI)

## Goal

When exactly one software source (repository) is temporarily broken — a bad
signature on its package index, an unreachable server, corrupt metadata — OneUp
must **update everything else and set only the broken source aside**, instead of
letting the whole system update fail. The "one-stop-shop" promise has to hold on
the day an upstream like Google's Chrome repo has a glitch.

## Background — why one bad source sinks the whole run today

Verified against `update_system.sh:525-616` (the `system` step):

1. The engine runs a single bulk `zypper refresh` (tracked in `refresh_ok`), then
   `zypper dup --allow-vendor-change` (Tumbleweed) / `zypper update` (Leap).
2. If **one** repo serves metadata zypper can't validate (bad signature / corrupt
   index), the non-interactive `dup` **aborts the entire transaction** — nothing
   from any repo installs. `ok=false`.
3. The failure branch matches `signature|GPG|key.*(expired|reject)` and emits
   `@@REMEDY@@|import-keys`, so the GUI offers **"Import signing key & retry."**

The gap: **`import-keys` is the wrong fix for a transient/index glitch.** Importing
a key only helps a genuinely *rotated/expired* key. For a temporary server-side
signature mismatch (the real Google-Chrome case), the retry fails again and the
engine then reports "still rejected even after importing keys" — a dead end that
forces a manual terminal session to disable the repo by hand. There is currently
**no way to set one bad source aside and finish the rest.**

## Scope decisions (agreed with the user)

- **Context-aware behaviour.**
  - **Manual run** (GUI "Update" button): OneUp *asks* — the warn banner offers
    **"Skip &lt;source&gt; & update the rest."** Nothing is disabled without a click.
  - **Unattended run** (weekly/tray automatic update, nobody watching): OneUp
    **auto-skips** the culprit, finishes the rest, and fires a desktop
    notification naming what was skipped.
- **Never weaken security.** The signature check (`gpgcheck`) is never disabled and
  a bad signature is never forced. The source is *temporarily disabled* with
  zypper's own on/off switch and **always re-enabled** afterward.
- **Both options on a genuinely expired key.** When the culprit's error is
  specifically an expired/rotated signing key, the manual banner offers **both**
  "Skip it" *and* the existing "Import signing key & retry" — so the user isn't
  pushed into skipping when a real fix exists. For every other glitch (broken
  index, unreachable server) it's just "Skip it."
- **Safety cap.** OneUp will skip at most `MAX_SKIP_REPOS` (= 2) sources in one
  run. If more than that are failing, that is a systemic problem (e.g. no network),
  not a one-off glitch: the run fails with a plain-English hint and does **not**
  silently skip half the system.
- **Automatic retry.** A skipped source is only *disabled for the duration of the
  run*, then re-enabled — so the next run tries it again with no persistent state.

## The mechanism (engine — `update_system.sh`)

The happy path is unchanged. All new work lives on the **failure path** and behind
two new flags, so a run where every repo is healthy never probes or touches repo
config.

### New CLI flags

```
--skip-repo=<alias>    Exclude this source from the run: disable it, upgrade the
                       rest, re-enable it. Repeatable. Alias is validated before
                       it reaches any privileged command.
--auto-skip-repos      Unattended mode: on a repo-scoped failure, auto-detect the
                       culprit(s), skip up to MAX_SKIP_REPOS of them, and continue.
                       Used only by the weekly/tray automatic path.
```

### Repo enable/disable + guaranteed restore

- Disable: `sudo zypper --non-interactive modifyrepo --disable "<alias>"`
  (mirrors the Repo-manager's existing `modifyrepo --disable` usage, ONEUP-0015/16).
- Re-enable: `sudo zypper --non-interactive modifyrepo --enable "<alias>"`.
- **Guaranteed restore:** every alias the engine disables is recorded in a
  `DISABLED_REPOS` list; the existing `cleanup()` function (`update_system.sh:325`)
  is extended to re-enable each one. `cleanup()` runs via `trap cleanup EXIT`
  (`:331`); the `INT`/`TERM`/`HUP` traps (`:332-333`) call `exit`, which fires that
  same EXIT trap — so a cancel (Ctrl-C), crash, or normal exit all restore repo
  state. Re-enabling runs `sudo zypper modifyrepo --enable` inside `cleanup()`; the
  sudo credential is still warm from the run, and if a re-enable fails the
  failure-mode below logs the exact command to fix it by hand.
- **Alias validation (bash).** Before any alias reaches a privileged `modifyrepo`,
  it is checked against `^[A-Za-z0-9][A-Za-z0-9:@._+-]*$` — the **identical**
  character class as the GUI's `_ALIAS_RE` (`updater.py:498`, applied with
  `.fullmatch()` in `_build_apply_command` at `:676`), which the Repo-manager
  already uses to refuse `evil; rm -rf /`. Matching it exactly matters: a real
  alias containing `@` or `+` must not be refused by the engine when the GUI would
  accept it, or that source would never be set aside and the whole update would
  still fail. A non-matching alias is refused and the repo is *not* skipped
  (fail-closed).

### Identifying the culprit(s) — `find_failing_repos()`

Only called on a repo-scoped failure (or in `--auto-skip-repos` mode). Deterministic
and alias-precise:

1. Enumerate **enabled** repos by alias from `LC_ALL=C zypper --non-interactive
   lr -u` — the same table form the engine's pre-flight already parses
   (`update_system.sh:503`) and the GUI's `_parse_repos` uses (`updater.py:501`):
   split each row on `|`, keep rows whose first column is a number, take the Alias
   column (2) for rows whose Enabled column (4) is `Yes`.
2. Refresh each enabled repo individually:
   `sudo zypper --non-interactive refresh "<alias>"`. Aliases whose refresh exits
   non-zero are the failing set. (Per-repo refresh, not bulk-output parsing, so we
   always hold the exact alias — the token `modifyrepo` needs.) **Classify each
   failing alias's `reason`** for the marker by grepping its own refresh output:
   `signature|GPG|key` → `signature`; `metadata|Valid metadata not found` →
   `metadata`; `Curl|could not resolve|Download.*failed|Timeout` → `unreachable`;
   anything else → `unreachable` (generic default). The `--skip-repo` path, where
   the culprit is named by the user rather than probed, uses `reason=manual`.

A "repo-scoped failure" worth probing = the `$SYS_LOG` matches
`signature|GPG|key|metadata|Valid metadata not found|Curl|could not resolve|Download.*failed|Skipping repository`.
Disk-full and package-conflict failures are **not** repo-scoped — they do not
trigger probing (unchanged behaviour).

### Failure-path flow (system step)

```
dup/update fails (ok=false) AND error is repo-scoped:
  failing = find_failing_repos()
  if |failing| == 0:                      # not actually a per-repo issue
      → existing hint behaviour (import-keys etc.), unchanged
  elif |failing| > MAX_SKIP_REPOS:        # systemic (e.g. network down)
      → @@HINT@@ "Several repositories are failing at once — likely a network or
        system problem, not a single bad source. Check your connection and retry."
      → end_step system fail            (no skipping)
  elif --auto-skip-repos (unattended):
      for alias in failing[:MAX_SKIP_REPOS]:
          validate; modifyrepo --disable; record in DISABLED_REPOS
          @@REPO_SKIPPED@@|alias|reason
      re-run dup/update on the remaining healthy repos
      if now ok: end_step system ok  (with a "skipped N source(s)" note)
      else:      end_step system fail (hint: skipping didn't clear it)
      # cleanup() re-enables all DISABLED_REPOS on exit
  else (manual/interactive):            # do NOT modify repos; ask the GUI
      for alias in failing[:MAX_SKIP_REPOS]:
          @@REMEDY@@|skip-repo|alias
      if error was an expired/rotated key: also @@REMEDY@@|import-keys
      @@HINT@@ naming the source(s) and that the rest can still be updated
      → end_step system fail            (user chooses in the GUI)
```

`--skip-repo=<alias>` mode (the GUI's re-run after the user clicks "Skip"): validate
each alias, `modifyrepo --disable`, record in `DISABLED_REPOS`, run the normal full
`dup`/`update`, emit `@@REPO_SKIPPED@@|alias|manual`. `cleanup()` re-enables on exit.

### New markers

```
@@REPO_SKIPPED@@|alias|reason   A source was set aside this run. reason ∈
                                {signature, metadata, unreachable, manual},
                                derived as in *Identifying the culprit(s)* above.
                                Emitted once per skipped source. GUI logs it,
                                and (unattended) the end-of-run notify names it.
@@REMEDY@@|skip-repo|alias      Interactive: tell the GUI to offer
                                "Skip <name> & update the rest" for this source.
```

Both must be added to the marker catalogue in `update_system.sh`'s header comment
(lines 103-119) **and** the `CLAUDE.md` "Current markers" list — the two files that
document the contract.

## GUI changes (`updater.py`)

- **`_launch(self, steps, check, import_keys=False, skip_repos=None)`** — the
  current signature is `_launch(self, steps, check, import_keys=False)`
  (`updater.py:1914`; `check` is a **required positional**, no default — keep it
  that way). Add a trailing `skip_repos` list and append one `--skip-repo=<alias>`
  per entry to the engine argv. The four current call-sites — `start_check`
  (`:1856`), `start_run` (`:1859`), `retry_failed` (`:1863`), `_fix_keys_and_retry`
  (`:1827`) — are unaffected (`skip_repos` defaults to none). (`request_size` is
  **not** a `_launch` call-site — it drives its own `--size` `QProcess`
  (`:1887`) — so it is untouched.)
- **`_headless_update()`** (unattended path, `tests/gui-smoke.py:205-215` proves it
  runs the engine with `--notify`) — add `--auto-skip-repos` to that engine argv,
  so the weekly/tray automatic run auto-quarantines.
- **`handle_marker`** (`updater.py:2022` — the interactive marker consumer):
  - `REPO_SKIPPED|alias|reason` → record the skipped source (for the log and the
    end-of-run summary). This is consumed **only on an interactive run**. The
    unattended path (`_headless_update`, `updater.py:2368`) runs the engine with
    `--notify` and does **no** GUI marker parsing (it reads only the exit code), so
    unattended reporting of a skipped source is entirely the engine's end-of-run
    `--notify`. (`_parse_tray_line` is *not* involved — it only handles `@@CHECK@@`
    on the read-only tray-check path, which never skips a repo.)
  - `REMEDY|skip-repo|alias` → arm a "skip" remedy: store the alias, and after the
    run finishes (`on_finished`) show the warn banner action **"Skip &lt;name&gt; &
    update the rest"**, where `<name>` is resolved from the alias via the existing
    `read_repos()` (fall back to the raw alias if lookup fails). Clicking it calls
    `_launch(steps, skip_repos=[alias])`.
- **Both remedies can be armed at once** (expired key): the banner shows the
  primary **"Skip it"** action and keeps the existing **"Import signing key &
  retry"** path reachable. Exact two-action banner layout is a plan detail; the
  invariant is that both are offered when the engine emits both markers. (The
  current warn banner is single-action — a `warn_btn` text-swap plus a separate
  `warn_copy_btn`; showing both actions at once needs a genuine second action
  button, not a text swap.)

## Correctness invariants (the tests must lock these in)

1. **Happy path untouched:** every repo healthy → no per-repo probing, no
   `modifyrepo` call, identical markers to today.
2. **Never weakens security:** no run ever passes `--no-gpg-checks`, disables
   `gpgcheck`, or force-imports a key to skip a source. (Test mock exits non-zero
   if `--no-gpg-checks` appears.)
3. **Guaranteed restore:** any repo the engine disables is re-enabled before the
   engine exits — on success, on failure, and on Ctrl-C/SIGTERM mid-run.
   (Test: after a `--skip-repo` run and after an interrupted run, a
   `modifyrepo --enable <alias>` was issued for every disabled alias.)
4. **Safety cap:** more than `MAX_SKIP_REPOS` failing → the run fails with the
   systemic-problem hint and issues **zero** `modifyrepo --disable` calls.
5. **Alias validated before root:** an unsafe alias (`evil; rm -rf /`) is refused —
   no `modifyrepo` command is built with it (mirrors the GUI guard test).
6. **Manual run never auto-skips:** without `--auto-skip-repos`, a repo-scoped
   failure emits `@@REMEDY@@|skip-repo` and fails the step; it issues **no**
   `modifyrepo --disable`. Skipping happens only on the GUI's `--skip-repo` re-run.
7. **Retry next run:** the skip is transient — no persistent `--disable` survives
   the run (covered by invariant 3).
8. **Reboot/success advice stays honest:** a run that skipped a source but upgraded
   the rest reports `@@STEP_END@@|system|ok` and normal reboot/service advice for
   what actually installed; a run where skipping did **not** clear the failure
   reports `fail` and advises no reboot (preserves the existing reboot invariant).
9. **Expired-key path keeps both remedies:** an expired-key failure in interactive
   mode emits **both** `@@REMEDY@@|skip-repo|<alias>` and `@@REMEDY@@|import-keys`.

## Failure modes

- **Network fully down** → all repos fail refresh → count > cap → systemic hint,
  no skipping. Correct: nothing to skip *to*.
- **`modifyrepo --disable` itself fails** (permissions, zypper busy) → the alias is
  not added to `DISABLED_REPOS`, the skip is abandoned for that repo, and the step
  fails with a hint rather than pretending success.
- **`modifyrepo --enable` restore fails on exit** → cleanup logs a plain-English
  warning naming the still-disabled alias and the one-line command to re-enable it,
  so the user is never silently left with a disabled repo.
- **Two sources broken (≤ cap)** → both skipped (unattended) or both offered
  (manual), rest updates.

## Tests

**Engine (`tests/run-tests.sh`)** — new mock scenarios:
- `--skip-repo=chrome` disables `chrome`, dup succeeds, `chrome` re-enabled on exit,
  `@@REPO_SKIPPED@@|chrome|manual` emitted.
- interrupted `--skip-repo` run still re-enables `chrome` (trap restore).
- `--auto-skip-repos` with one failing repo: skipped, rest upgraded,
  `@@STEP_END@@|system|ok`, notify names the skipped source.
- `--auto-skip-repos` with 3 failing repos (> cap): systemic hint, **no**
  `modifyrepo --disable`, step fails.
- manual repo-scoped failure (no `--auto-skip-repos`): `@@REMEDY@@|skip-repo`
  emitted, **no** `modifyrepo --disable`, step fails.
- unsafe alias refused (no privileged command built).
- no run ever passes `--no-gpg-checks` (guard mock).
- happy path: all repos healthy → no `modifyrepo`, no `refresh <alias>` probing.

**GUI (`tests/gui-smoke.py`):**
- `_launch(..., skip_repos=["chrome"])` puts `--skip-repo=chrome` in the engine argv.
- `_headless_update()` engine argv contains `--auto-skip-repos`.
- `REMEDY|skip-repo|chrome` arms the "Skip … & update the rest" banner action; the
  label resolves the source name via `read_repos`.
- clicking the skip action calls `_launch` with `skip_repos=["chrome"]`.
- both remedies armed (skip + import-keys) → both actions reachable.

## Docs & release

- `CHANGELOG.md` `[Unreleased] / Added`: a plain-English bullet.
- `README.md` "What it does": one line on surviving a broken source.
- `CLAUDE.md`: add `REPO_SKIPPED` and `REMEDY|skip-repo` to the marker list;
  note the `--skip-repo` / `--auto-skip-repos` flags.
- No version bump in this feature branch (batched into the next release via `bump.py`).

## Alternatives considered (and rejected)

- **`zypper dup --repo <healthy…>`** (restrict the upgrade to healthy repos) —
  rejected: restricting `dup` changes its distribution-upgrade semantics against a
  partial repo set, which is unsafe on Tumbleweed. Disabling the one bad repo and
  running a normal full `dup` keeps every other repo participating exactly as usual.
- **`--gpg-auto-import-keys` / `--no-gpg-checks` to push past it** — rejected:
  that trusts an unverified source. The whole point is to *set aside*, never *force*.
- **Parsing the `dup` failure output for the repo name** — rejected: zypper reports
  the repo *name*, but `modifyrepo` needs the *alias*/number. Per-repo refresh yields
  the exact alias deterministically and locale-independently (`LC_ALL=C`).
- **Persisting a "known-bad" list to skip on future runs** — rejected (YAGNI):
  a transient glitch clears on its own; a persistent disable would hide a real,
  lasting problem. Retry-every-run is simpler and self-healing.

## Out of scope

- Pre-flight detection in `--check` (surfacing "a source looks unhealthy" *before* a
  run) — a possible follow-up, not required here.
- A GUI list/history view of previously-skipped sources beyond the per-run log line.
- Any change to the Flatpak/firmware/orphans/cache steps — this is the `system`
  step only.
