# ONEUP-0025 — Repo resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When one software source is broken (bad signature / unreachable / corrupt index), OneUp sets *only that source* aside, updates everything else, and retries it next run — instead of the whole system update failing.

**Architecture:** All engine logic lives on the `system`-step **failure path** and behind two new flags, so a healthy run never probes or touches repo config. The GUI gains a `skip_repos` arg to `_launch`, passes `--auto-skip-repos` on the unattended path, and offers a "Skip &lt;source&gt; & update the rest" banner action on a manual run.

**Tech Stack:** Bash (`update_system.sh`, `set -uo pipefail`), PySide6/Qt 6 (`updater.py`), mock-`PATH` engine tests (`tests/run-tests.sh`), headless GUI smoke tests (`tests/gui-smoke.py`).

**Spec:** `docs/specs/ONEUP-0025-repo-resilience.md` (cold-eyes converged). Read it first — it holds the exact contracts; this plan holds the code.

## Global Constraints

- **Never weaken security.** No run ever passes `--no-gpg-checks`, disables `gpgcheck`, or force-imports a key to skip a source. A source is *disabled* (set aside), never *forced/trusted*.
- **Privilege split.** `updater.py` never runs as root; it shells out to `update_system.sh` via `QProcess`. All `sudo`/`modifyrepo` calls live in the engine. Match the `sudo` (ASKPASS) pattern already in the engine.
- **Marker contract lives in both files.** Any new `@@MARKER@@` is added to the catalogue comment in `update_system.sh` (lines 103-119) **and** the "Current markers" list in `CLAUDE.md`, and asserted in the tests.
- **Reboot honesty preserved.** A run that skipped a source but upgraded the rest reports `@@STEP_END@@|system|ok` with normal reboot/service advice for what actually installed; a run where skipping didn't clear the failure reports `fail` and advises no reboot.
- **Alias safety.** Every repo alias is validated against `^[A-Za-z0-9][A-Za-z0-9:@._+-]*$` (identical char class to `updater.py`'s `_ALIAS_RE`) before it reaches any privileged `modifyrepo`. Fail-closed: a non-matching alias is refused, the repo is *not* skipped.
- **Guaranteed restore.** Every repo the engine disables is re-enabled before exit — on success, failure, and Ctrl-C/SIGTERM — via the `cleanup()`/`trap` machinery.
- **Safety cap.** `MAX_SKIP_REPOS=2`: more than that failing → systemic problem → fail with a hint, skip nothing.
- **Skip absent tools cleanly** and keep the happy path byte-for-byte unchanged.

---

### Task 1: Engine primitives + the `--skip-repo` path (disable → upgrade → restore)

The smallest end-to-end slice: the flags, the alias guard, `disable_repo`, the `cleanup()` restore extension, the `REPO_SKIPPED` marker, and the up-front `--skip-repo` disable. This is exactly the GUI's "Skip & retry" re-run path.

**Files:**
- Modify: `update_system.sh` (globals ~35-44; arg parse ~74-85; marker catalogue 103-119; `cleanup()` ~325; `system` step 525-616)
- Test: `tests/run-tests.sh`

**Interfaces (produced, used by Tasks 2-3):**
- Globals: `SKIP_REPOS=()`, `AUTO_SKIP=false`, `DISABLED_REPOS=()`, `MAX_SKIP_REPOS=2`.
- `valid_alias <alias>` → exit 0 iff safe.
- `disable_repo <alias> <reason>` → validates, `modifyrepo --disable`, on success appends to `DISABLED_REPOS` and emits `@@REPO_SKIPPED@@|alias|reason`; exit non-zero on refusal/failure.
- `run_system_upgrade` → runs the `dup`/`update` transaction into `$SYS_LOG`, sets global `ok`.

- [ ] **Step 1: Write the failing tests** (`tests/run-tests.sh`, append new scenarios)

```bash
# ---------------------------------------------------------------------------
echo "TEST: --skip-repo disables the named source, upgrades the rest, re-enables on exit"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
echo "zypper $*" >> "$MOCK_ZLOG"
case "$*" in
  *"modifyrepo --disable"*) exit 0 ;;
  *"modifyrepo --enable"*)  exit 0 ;;
  *refresh*)                exit 0 ;;
  *dup*|*update*)           echo "3 packages to upgrade."; exit 0 ;;
  *needs-rebooting*)        exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
export MOCK_ZLOG="$d/zypper.log"; : > "$MOCK_ZLOG"
out=$(run_engine "$d" --steps=system --skip-repo=google-chrome)
check        "skip-repo disables the source"        "modifyrepo --disable google-chrome" "$(cat "$MOCK_ZLOG")"
check        "skip-repo emits the REPO_SKIPPED mark" "@@REPO_SKIPPED@@|google-chrome|manual" "$out"
check        "skip-repo upgrade still succeeds"      "@@STEP_END@@|system|ok" "$out"
check        "skipped source re-enabled on exit"     "modifyrepo --enable google-chrome" "$(cat "$MOCK_ZLOG")"
unset MOCK_ZLOG

# ---------------------------------------------------------------------------
echo "TEST: an interrupted --skip-repo run still re-enables the source (trap restore)"
d=$(mktemp -d); setup_common "$d"
export MOCK_ZLOG="$d/zypper.log"; : > "$MOCK_ZLOG"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
echo "zypper $*" >> "$MOCK_ZLOG"
case "$*" in
  *"modifyrepo --disable"*) exit 0 ;;
  *"modifyrepo --enable"*)  exit 0 ;;
  *refresh*)                exit 0 ;;
  *dup*|*update*)           kill -TERM $PPID; sleep 5; exit 0 ;;   # die mid-upgrade
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
run_engine "$d" --steps=system --skip-repo=google-chrome >/dev/null 2>&1 || true
check "interrupted run re-enabled the source" "modifyrepo --enable google-chrome" "$(cat "$MOCK_ZLOG")"
unset MOCK_ZLOG

# ---------------------------------------------------------------------------
echo "TEST: an unsafe repo alias is refused and never reaches a privileged command"
d=$(mktemp -d); setup_common "$d"
export MOCK_ZLOG="$d/zypper.log"; : > "$MOCK_ZLOG"
printf '#!/usr/bin/env bash\necho "zypper $*" >> "$MOCK_ZLOG"\ncase "$*" in *dup*|*update*) echo "Nothing to do."; exit 0;; *) exit 0;; esac\n' > "$d/zypper"
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system "--skip-repo=evil; rm -rf /")
check_absent "unsafe alias never reaches modifyrepo" "modifyrepo --disable evil" "$(cat "$MOCK_ZLOG")"
unset MOCK_ZLOG
```

> Note for the implementer: `setup_common` / `run_engine` / `check` / `check_absent` are the existing test helpers. If `run_engine` doesn't already export the mock dir onto `PATH` such that a `MOCK_ZLOG` env survives, pass it through as these tests do (`export` before `run_engine`). Confirm the harness forwards env; adjust if needed.

- [ ] **Step 2: Run the tests, confirm they FAIL** (`tests/run-tests.sh`) — expect failures: unknown flag `--skip-repo`, no `REPO_SKIPPED`, no enable/disable.

- [ ] **Step 3: Add globals + arg parsing** (`update_system.sh`)

Near the other option globals (~line 35-44):
```bash
SKIP_REPOS=()      # --skip-repo=<alias> (repeatable): sources to set aside this run
AUTO_SKIP=false    # --auto-skip-repos: unattended auto-quarantine of a broken source
DISABLED_REPOS=()  # aliases WE disabled this run; cleanup() re-enables every one
MAX_SKIP_REPOS=2   # more than this failing at once = systemic, don't silently skip
```
In the arg-parse `case` (~line 74-85), add:
```bash
        --skip-repo=*)     SKIP_REPOS+=("${arg#*=}") ;;
        --auto-skip-repos) AUTO_SKIP=true ;;
```
Add to `usage()` (~line 49-65) two lines mirroring the spec's flag descriptions.

- [ ] **Step 4: Add helpers + extend `cleanup()`** (`update_system.sh`)

Add helpers just above the `system` step (after the pre-flight section):
```bash
# --- repo resilience: set a broken source aside instead of failing the whole run ---
valid_alias() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9:@._+-]*$ ]]; }

disable_repo() {   # $1=alias $2=reason ; records + marks on success, fail-closed
    local alias="$1" reason="$2"
    valid_alias "$alias" || { echo "  Refusing unsafe repo alias: $alias" >&2; return 1; }
    if sudo zypper --non-interactive modifyrepo --disable "$alias" >/dev/null 2>&1; then
        DISABLED_REPOS+=("$alias"); marker REPO_SKIPPED "$alias|$reason"; return 0
    fi
    return 1
}
```
Extend `cleanup()` (line 325) — re-enable **before** killing the keep-alive (sudo cred still warm), non-interactively so a cold-credential exit logs the manual fix instead of blocking on a popup:
```bash
cleanup() {
    local a
    for a in "${DISABLED_REPOS[@]:-}"; do
        [[ -z "$a" ]] && continue
        sudo -n zypper --non-interactive modifyrepo --enable "$a" >/dev/null 2>&1 \
            || echo "  ! Couldn't re-enable repository '$a' — run: sudo zypper modifyrepo --enable $a" >&2
    done
    [[ -n "$SUDO_KEEPALIVE" ]] && kill -- "-$SUDO_KEEPALIVE" 2>/dev/null
}
```

- [ ] **Step 5: Factor the transaction into `run_system_upgrade` + disable `SKIP_REPOS` up front** (`update_system.sh`, in the `system` step)

Replace the inline `ok=true … dup/update … | tee "$SYS_LOG"` block with a function defined once (near the helpers):
```bash
run_system_upgrade() {   # runs the transaction into $SYS_LOG (truncates it); sets global `ok`
    ok=true
    if [[ -f /etc/os-release ]] && grep -q "Leap" /etc/os-release; then
        sudo env LC_ALL=C zypper --non-interactive update 2>&1 | tee "$SYS_LOG"
    else
        sudo env LC_ALL=C zypper --non-interactive dup --allow-vendor-change 2>&1 | tee "$SYS_LOG"
    fi
    [[ ${PIPESTATUS[0]} -eq 0 ]] || ok=false
}
```
In the step, right after `begin_step system` and before the refresh, disable any GUI-named sources:
```bash
    # Interactive "Skip & update the rest" re-run: set the named sources aside up front.
    for alias in "${SKIP_REPOS[@]:-}"; do
        [[ -z "$alias" ]] && continue
        disable_repo "$alias" manual || true
    done
```
Keep the existing refresh block. Then `SYS_LOG=$(mktemp)` and call `run_system_upgrade` in place of the old inline transaction. (`tee` truncates `$SYS_LOG`, so re-runs in Task 3 are clean.)

- [ ] **Step 6: Add the two markers to the catalogue** (`update_system.sh` lines 103-119)
```
#   @@REPO_SKIPPED@@|alias|reason        (a source was set aside this run)
#   @@REMEDY@@|skip-repo|alias           (offer "Skip <source> & update the rest")
```

- [ ] **Step 7: Run the Task-1 tests, confirm they PASS.** Then run the FULL suite (`tests/run-tests.sh`) — the happy-path tests must stay green (no behaviour change when `SKIP_REPOS` is empty).

- [ ] **Step 8: Commit** — `git add update_system.sh tests/run-tests.sh && git commit -m "ONEUP-0025: engine --skip-repo path (disable→upgrade→restore) + REPO_SKIPPED marker"`

---

### Task 2: Engine — enumerate enabled repos + `find_failing_repos` with reason classification

Pure helpers, independently testable.

**Files:**
- Modify: `update_system.sh` (add `enabled_repo_aliases`, `find_failing_repos`, `repo_scoped_failure` near the Task-1 helpers)
- Test: `tests/run-tests.sh`

**Interfaces (produced, used by Task 3):**
- `enabled_repo_aliases` → prints one alias per **enabled** repo (from `zypper lr -u`, no root).
- `find_failing_repos` → prints `alias reason` per enabled repo whose individual `refresh` fails; reason ∈ {signature, metadata, unreachable}.
- `repo_scoped_failure` → exit 0 iff `$SYS_LOG` matches the repo-scoped error patterns.

- [ ] **Step 1: Write the failing test** — a mock where `lr -u` lists two enabled + one disabled repo, and per-repo `refresh` fails for one with a signature error.

```bash
# ---------------------------------------------------------------------------
echo "TEST: find_failing_repos names the failing enabled repo and classifies the reason"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"lr -u"*) printf '#  | Alias  | Name | Enabled | GPG Check | Refresh | URI\n---+--------+------+---------+-----------+---------+----\n1  | oss    | O    | Yes     | Yes       | Yes     | http://o/\n2  | chrome | C    | Yes     | Yes       | Yes     | http://c/\n3  | off    | X    | No      | Yes       | Yes     | http://x/\n'; exit 0 ;;
  *"refresh chrome"*) echo "Signature verification failed for repository 'chrome'"; exit 1 ;;
  *"refresh oss"*)    exit 0 ;;
  *"refresh off"*)    exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
# Drive the helper directly through a tiny harness the engine exposes under a test hook,
# OR assert via the Task-3 integration below. Preferred: source-and-call in a subshell:
out=$(cd "$d" && PATH="$d:$PATH" bash -c 'source "'"$PWD"'/update_system.sh" --self-test-find-failing 2>/dev/null' 2>/dev/null || true)
```

> **Implementer decision to resolve:** the engine is a run-to-completion script, not a sourceable library, so a clean unit call needs a hook. Two options — pick the lower-risk one and note it in the report: (a) add a hidden `--self-test-find-failing` arg that runs `find_failing_repos` and exits (tiny, test-only, guarded); or (b) skip the isolated unit test and cover `find_failing_repos` entirely through Task 3's integration tests (auto-skip picks exactly `chrome`). **Recommendation: (b)** — no production surface added for tests; Task 3 already exercises every branch. If you choose (b), delete this step's isolated test and rely on Task 3.

- [ ] **Step 2: Implement the helpers** (`update_system.sh`)
```bash
enabled_repo_aliases() {   # alias of each ENABLED repo (read-only; no root)
    LC_ALL=C zypper --non-interactive lr -u 2>/dev/null | awk -F'|' '
        { for (i=1;i<=NF;i++) gsub(/^ +| +$/,"",$i) }
        $1 ~ /^[0-9]+$/ && tolower(substr($4,1,1))=="y" { print $2 }'
}

find_failing_repos() {     # "alias reason" per enabled repo that fails its own refresh
    local alias out rc reason
    while IFS= read -r alias; do
        [[ -z "$alias" ]] && continue
        out=$(sudo zypper --non-interactive refresh "$alias" 2>&1); rc=$?
        (( rc == 0 )) && continue
        if   grep -qiE 'signature|GPG|key' <<<"$out"; then reason=signature
        elif grep -qiE 'metadata|Valid metadata not found' <<<"$out"; then reason=metadata
        else reason=unreachable; fi
        echo "$alias $reason"
    done < <(enabled_repo_aliases)
}

repo_scoped_failure() {
    grep -qiE 'signature|GPG|key|metadata|Valid metadata not found|Curl|could not resolve|Download.*failed|Skipping repository' "$SYS_LOG"
}
```

- [ ] **Step 3: Run the test** (or defer to Task 3 per the decision above), confirm behaviour.
- [ ] **Step 4: Commit** — `git commit -m "ONEUP-0025: engine repo enumeration + find_failing_repos (reason classification)"`

---

### Task 3: Engine — failure-path integration (auto-skip, interactive-detect, safety cap)

Wire the helpers into the `system` step's failure path.

**Files:**
- Modify: `update_system.sh` (`system` step, between `run_system_upgrade` and the `if $ok` block; the success and fail branches; the end-of-run notify block ~804-815)
- Test: `tests/run-tests.sh`

- [ ] **Step 1: Write the failing tests**
```bash
# ---------------------------------------------------------------------------
echo "TEST: --auto-skip-repos sets a broken source aside, upgrades the rest, reports ok + notifies"
d=$(mktemp -d); setup_common "$d"
export MOCK_ZLOG="$d/zypper.log"; : > "$MOCK_ZLOG"
cat > "$d/notify-send" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$MOCK_NLOG"
EOF
chmod +x "$d/notify-send"; export MOCK_NLOG="$d/notify.log"; : > "$MOCK_NLOG"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
echo "zypper $*" >> "$MOCK_ZLOG"
case "$*" in
  *"lr -u"*)               printf '# | Alias | Name | Enabled | GPG | Refresh | URI\n1 | oss | O | Yes | Yes | Yes | http://o/\n2 | chrome | C | Yes | Yes | Yes | http://c/\n'; exit 0 ;;
  *"modifyrepo --disable chrome"*) exit 0 ;;
  *"modifyrepo --enable chrome"*)  exit 0 ;;
  *"refresh chrome"*)      echo "Signature verification failed for repository 'chrome'"; exit 1 ;;
  *"refresh oss"*)         exit 0 ;;
  *refresh*)               exit 0 ;;                                   # bulk refresh
  *dup*|*update*)
      if grep -q "modifyrepo --disable chrome" "$MOCK_ZLOG"; then echo "2 packages to upgrade."; exit 0   # retry after skip: OK
      else echo "Signature verification failed for repository 'chrome'"; exit 1; fi ;;                     # first attempt: blocked
  *needs-rebooting*)       exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system --auto-skip-repos --notify)
check        "auto-skip disables the culprit"       "modifyrepo --disable chrome" "$(cat "$MOCK_ZLOG")"
check        "auto-skip emits REPO_SKIPPED"          "@@REPO_SKIPPED@@|chrome|signature" "$out"
check        "auto-skip upgrade then succeeds"       "@@STEP_END@@|system|ok" "$out"
check        "auto-skip re-enables the culprit"      "modifyrepo --enable chrome" "$(cat "$MOCK_ZLOG")"
check_re     "notify names the skipped source"       "chrome" "$(cat "$MOCK_NLOG")"
check_absent "auto-skip never disables gpg checks"   "--no-gpg-checks" "$(cat "$MOCK_ZLOG")"
unset MOCK_ZLOG MOCK_NLOG

# ---------------------------------------------------------------------------
echo "TEST: a manual repo-scoped failure OFFERS skip (no --auto-skip-repos), disables nothing"
d=$(mktemp -d); setup_common "$d"
export MOCK_ZLOG="$d/zypper.log"; : > "$MOCK_ZLOG"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
echo "zypper $*" >> "$MOCK_ZLOG"
case "$*" in
  *"lr -u"*)          printf '# | Alias | Name | Enabled | GPG | Refresh | URI\n1 | oss | O | Yes | Yes | Yes | http://o/\n2 | chrome | C | Yes | Yes | Yes | http://c/\n'; exit 0 ;;
  *"refresh chrome"*) echo "Signature verification failed for repository 'chrome' (key expired)"; exit 1 ;;
  *"refresh oss"*)    exit 0 ;;
  *refresh*)          exit 0 ;;
  *dup*|*update*)     echo "Signature verification failed for repository 'chrome' (key expired)"; exit 1 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check        "manual failure offers skip for the culprit"   "@@REMEDY@@|skip-repo|chrome" "$out"
check        "expired key ALSO offers the import remedy"     "@@REMEDY@@|import-keys" "$out"
check        "manual failure fails the step"                 "@@STEP_END@@|system|fail" "$out"
check_absent "manual failure disables nothing on its own"    "modifyrepo --disable" "$(cat "$MOCK_ZLOG")"
unset MOCK_ZLOG

# ---------------------------------------------------------------------------
echo "TEST: more than the cap failing = systemic; hint, no skipping"
d=$(mktemp -d); setup_common "$d"
export MOCK_ZLOG="$d/zypper.log"; : > "$MOCK_ZLOG"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
echo "zypper $*" >> "$MOCK_ZLOG"
case "$*" in
  *"lr -u"*)   printf '# | Alias | Name | Enabled | GPG | Refresh | URI\n1 | a | A | Yes | Yes | Yes | http://a/\n2 | b | B | Yes | Yes | Yes | http://b/\n3 | c | C | Yes | Yes | Yes | http://c/\n'; exit 0 ;;
  *refresh\ a*|*refresh\ b*|*refresh\ c*) echo "could not resolve host"; exit 1 ;;
  *refresh*)   exit 1 ;;
  *dup*|*update*) echo "could not resolve host name"; exit 1 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system --auto-skip-repos)
check        "systemic failure hints network/system"  "@@HINT@@|Several repositories are failing" "$out"
check_absent "systemic failure disables nothing"      "modifyrepo --disable" "$(cat "$MOCK_ZLOG")"
check        "systemic failure fails the step"         "@@STEP_END@@|system|fail" "$out"
unset MOCK_ZLOG

# ---------------------------------------------------------------------------
echo "TEST: a manual over-cap failure offers no skip"
# (same lr -u as the systemic mock; run WITHOUT --auto-skip-repos)
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"lr -u"*)   printf '# | Alias | Name | Enabled | GPG | Refresh | URI\n1 | a | A | Yes | Yes | Yes | http://a/\n2 | b | B | Yes | Yes | Yes | http://b/\n3 | c | C | Yes | Yes | Yes | http://c/\n'; exit 0 ;;
  *refresh\ *) echo "could not resolve host"; exit 1 ;;
  *refresh*)   exit 1 ;;
  *dup*|*update*) echo "could not resolve host name"; exit 1 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check_absent "manual over-cap offers no skip" "@@REMEDY@@|skip-repo" "$out"
```

- [ ] **Step 2: Run the tests, confirm they FAIL.**

- [ ] **Step 3: Implement the failure-path block** (`update_system.sh`) — insert between `run_system_upgrade` (first call) and the `if $ok` block:
```bash
    # Repo resilience: a repo-scoped failure need not sink the whole run. Only probe
    # when we weren't already told which to skip (a --skip-repo run named them).
    systemic_repo_fail=false
    if ! $ok && (( ${#SKIP_REPOS[@]} == 0 )) && repo_scoped_failure; then
        mapfile -t failing < <(find_failing_repos)
        if (( ${#failing[@]} > MAX_SKIP_REPOS )); then
            systemic_repo_fail=true                       # too many → not one bad source
        elif (( ${#failing[@]} > 0 )); then
            if $AUTO_SKIP; then
                for entry in "${failing[@]}"; do
                    disable_repo "${entry%% *}" "${entry#* }" || true
                done
                (( ${#DISABLED_REPOS[@]} > 0 )) && run_system_upgrade   # retry on healthy repos
            else
                for entry in "${failing[@]}"; do marker REMEDY "skip-repo|${entry%% *}"; done
            fi
        fi
    fi
```
In the **success** branch (`if $ok`), after the existing count handling, add a skipped-source note:
```bash
        if (( ${#DISABLED_REPOS[@]} > 0 )); then
            note="Updated everything except: ${DISABLED_REPOS[*]} — set aside this run (temporary problem); OneUp will retry next time."
            echo "  Note: $note"; marker HINT "$note"
        fi
```
In the **fail** branch, add the systemic hint as the FIRST case so it wins over import-keys:
```bash
        if $systemic_repo_fail; then
            hint="Several repositories are failing at once — likely a network or system problem, not a single bad source. Check your connection and retry."
        elif grep -qiE 'No space left|disk full' "$SYS_LOG"; then
        ...   # (existing cases unchanged)
```

- [ ] **Step 4: Extend the end-of-run notify** (`update_system.sh` ~804-815) — when `DISABLED_REPOS` is non-empty, include the skipped source name(s) in the notification text so an unattended run reports them. Read the existing block and append to its message; keep the existing wording for the no-skip case.

- [ ] **Step 5: Run the Task-3 tests + the FULL suite, confirm all PASS** (esp. every pre-existing system-step test stays green).

- [ ] **Step 6: Commit** — `git commit -m "ONEUP-0025: engine failure-path — auto-skip, interactive skip-offer, safety cap"`

---

### Task 4: Docs — CLAUDE.md markers, CHANGELOG, README

**Files:** Modify `CLAUDE.md`, `CHANGELOG.md`, `README.md`.

- [ ] **Step 1:** `CLAUDE.md` "Current markers" list — add `REPO_SKIPPED` and note `REMEDY|skip-repo`; mention the `--skip-repo` / `--auto-skip-repos` flags alongside the marker prose.
- [ ] **Step 2:** `CHANGELOG.md` `[Unreleased] / Added` — one plain-English bullet:
  > **OneUp now survives a single broken software source instead of failing the whole update.** When one repository serves a bad signature or is unreachable, OneUp sets just that source aside, updates everything else, and retries it next time. A manual run offers "Skip &lt;source&gt; & update the rest"; an unattended run skips it automatically and tells you. It never weakens the signature check — the source is only set aside, never forced.
- [ ] **Step 3:** `README.md` "What it does" — one bullet on surviving a broken source.
- [ ] **Step 4: Commit** — `git commit -m "ONEUP-0025: document repo resilience (CLAUDE.md markers, CHANGELOG, README)"`

---

### Task 5: GUI — `_launch(skip_repos=…)` + `_headless_update` auto-skip

**Files:**
- Modify: `updater.py` (`_launch` ~1914; `_headless_update` ~2368)
- Test: `tests/gui-smoke.py`

- [ ] **Step 1: Write the failing tests** (`tests/gui-smoke.py`)
```python
    # --- repo-resilience: skip_repos threads through to the engine argv -----------
    w = updater.Updater()
    captured = {}
    w._start_engine = getattr(w, "_start_engine", None)   # keep if present
    # Intercept the QProcess start inside _launch by stubbing the process factory it uses.
    # Simplest: call the argv-builder path _launch uses and assert the flags. If _launch
    # builds argv inline, refactor the argv assembly into a tiny helper `_engine_args`
    # (steps, check, import_keys, skip_repos) and assert on THAT (see Step 3).
    args = updater.Updater._engine_args(["system"], check=False, import_keys=False,
                                        skip_repos=["google-chrome"])
    check("skip_repos adds one --skip-repo per alias", "--skip-repo=google-chrome" in args)
    check("no skip_repos → no --skip-repo flag",
          "--skip-repo" not in " ".join(updater.Updater._engine_args(["system"], check=False)))

    # --- unattended update passes --auto-skip-repos ------------------------------
    _cap = {}
    _orig = updater.subprocess.run
    updater.subprocess.run = lambda a, *ar, **kw: (_cap.update(argv=a) or type("R", (), {"returncode": 0})())
    try:
        updater._headless_update()
    finally:
        updater.subprocess.run = _orig
    check("headless update auto-skips broken sources",
          "--auto-skip-repos" in _cap.get("argv", []))
```

- [ ] **Step 2: Run, confirm FAIL** (no `_engine_args`, no `--auto-skip-repos`).

- [ ] **Step 3: Implement** (`updater.py`) — extract the engine-argv assembly `_launch` already does into a small static/staticmethod-friendly helper so it's unit-testable, then have `_launch` use it and add `skip_repos`:
```python
    @staticmethod
    def _engine_args(steps, check=False, import_keys=False, skip_repos=None):
        args = [str(ENGINE), f"--steps={','.join(steps)}"]
        if check:       args.append("--check")
        if import_keys: args.append("--import-keys")
        for alias in (skip_repos or []):
            args.append(f"--skip-repo={alias}")
        return args
```
> Match the EXISTING argv `_launch` builds (steps/check/import_keys order and the `--log=` it appends at call time). Keep `--log=` where it currently is; `_engine_args` covers only the stable flags. Then:
```python
    def _launch(self, steps, check, import_keys=False, skip_repos=None):
        # ... existing empty-steps guard ...
        # build argv via self._engine_args(steps, check, import_keys, skip_repos)
        # ... plus the existing --log=<path> append + QProcess start ...
```
In `_headless_update()` add `--auto-skip-repos`:
```python
    return subprocess.run(["bash", str(ENGINE), "--notify", "--auto-skip-repos"]).returncode
```
> The gui-smoke guard "headless `--update` invokes the engine with `--notify`, not `--update`" (lines 205-215) must stay green — `--auto-skip-repos` is additive.

- [ ] **Step 4: Run the tests, confirm PASS.** Run the FULL gui-smoke suite.
- [ ] **Step 5: Commit** — `git commit -m "ONEUP-0025: GUI _launch skip_repos + unattended --auto-skip-repos"`

---

### Task 6: GUI — `REPO_SKIPPED` logging + the "Skip &lt;source&gt; & update the rest" banner action

**Files:**
- Modify: `updater.py` (`handle_marker` ~2022; `on_finished` remedy handling ~2200-2215; the warn banner ~1010/1940)
- Test: `tests/gui-smoke.py`

- [ ] **Step 1: Write the failing tests** (`tests/gui-smoke.py`)
```python
    # --- REPO_SKIPPED is recorded; skip-repo remedy arms a named banner action ----
    w = updater.Updater()
    w.read_repos = lambda: [{"alias": "google-chrome", "name": "Google Chrome",
                             "enabled": True, "url": "http://c/"}]
    w.handle_line("@@REPO_SKIPPED@@|google-chrome|signature")
    check("REPO_SKIPPED recorded", "google-chrome" in getattr(w, "_skipped_repos", []))

    w.handle_line("@@REMEDY@@|skip-repo|google-chrome")
    check("skip-repo remedy stores the alias", getattr(w, "_remedy_skip", None) == "google-chrome")
    w._failed_steps = ["system"]
    w.proc = QProcess(w)
    w.on_finished(1, QProcess.ExitStatus.NormalExit)
    check("banner offers a NAMED skip action",
          "Google Chrome" in w.warn_btn.text() and "Skip" in w.warn_btn.text())

    # clicking it re-launches with skip_repos = the alias
    launched = {}
    w._launch = lambda steps, check=False, import_keys=False, skip_repos=None: launched.update(
        steps=list(steps), skip=list(skip_repos or []))
    w._skip_repo_and_retry()
    check("skip action re-launches with the alias", launched.get("skip") == ["google-chrome"])
    check("skip action re-runs the failed steps", launched.get("steps") == ["system"])
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Implement** (`updater.py`)
- Init (in `__init__`): `self._skipped_repos = []` and `self._remedy_skip = None`.
- In `handle_marker`, add:
```python
        elif tag == "REPO_SKIPPED":
            if parts:
                alias = parts[0]
                self._skipped_repos.append(alias)
                self.log.appendPlainText(f"  Set aside this run: {alias} (will retry next time)")
        elif tag == "REMEDY":
            if parts and parts[0] == "import-keys":
                self._remedy_keys = True
            elif parts and parts[0] == "skip-repo" and len(parts) >= 2:
                self._remedy_skip = parts[1]          # the alias to offer skipping
```
- Add the retry slot + a name resolver:
```python
    def _repo_display_name(self, alias):
        for r in self.read_repos():
            if r.get("alias") == alias:
                return r.get("name") or alias
        return alias

    def _skip_repo_and_retry(self):
        alias = self._remedy_skip
        if not alias:
            return
        steps = list(self._failed_steps) or ["system"]
        self._launch(steps, check=False, skip_repos=[alias])
```
- In `on_finished` where remedies are surfaced (~2200-2215), when `self._remedy_skip` is set, show the warn banner with primary action text `f"Skip {self._repo_display_name(self._remedy_skip)} & update the rest"` wired to `_skip_repo_and_retry`. When BOTH `_remedy_skip` and `_remedy_keys` are set, the skip action is primary and the "Import signing key & retry" path stays reachable.
> **Two-action banner:** the current banner drives a single action via `warn_btn`'s text/slot swap plus a separate `warn_copy_btn`. Offering skip *and* import-keys together needs a genuine second action button. Add one `warn_btn2` next to `warn_btn` (mirror `warn_copy_btn`'s construction and visibility toggling); show it only when both remedies are armed. Keep the single-action path unchanged when only one remedy is armed. Reset `_remedy_skip`/`_remedy_keys`/`warn_btn2` visibility at the start of each run (mirror how `_remedy_keys` is reset today).

- [ ] **Step 4: Run the tests, confirm PASS.** Run the FULL gui-smoke suite.
- [ ] **Step 5: Commit** — `git commit -m "ONEUP-0025: GUI skip-source banner action + REPO_SKIPPED logging"`

---

## Final gate (after all tasks)

- [ ] `./local-CI.sh` green (engine + gui-smoke suites, lint, validation, version-lockstep).
- [ ] Whole-branch review (superpowers:requesting-code-review) on the most capable model, pointed at the branch diff and this plan's Global Constraints.
- [ ] `superpowers:finishing-a-development-branch` → merge to main locally (matches the tray-icon flow), flip ONEUP-0025 to ✅ with a resolution note.

## Notes for the implementer

- **`set -uo pipefail` is on.** Guard array expansions with `"${arr[@]:-}"` and length checks with `${#arr[@]}` (safe on empty declared arrays). The engine has a load-bearing comment about this at line 129 — follow it.
- **`MOCK_ZLOG`/`MOCK_NLOG`** are test-only conveniences these tests introduce; confirm `run_engine` forwards exported env into the mock `PATH` (the existing key-import tests already rely on `MOCK_KEYDIR`, so the pattern is established — mirror it).
- **Do not** add a `--no-gpg-checks` path or disable `gpgcheck` anywhere — a test asserts its absence.
- **Reuse, don't reinvent:** `marker`, `begin_step`/`end_step`, `read_repos`/`_parse_repos`, `_ALIAS_RE`, the warn-banner helpers, and `cleanup()`/`trap` all already exist — extend them.
