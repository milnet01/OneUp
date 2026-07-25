#!/usr/bin/env bash
#
# OneUp engine tests. No dependencies beyond bash + coreutils: each test builds a
# throwaway PATH of mock system tools (zypper, flatpak, sudo, …) so the real
# machine is never touched, runs update_system.sh, and asserts on the @@MARKER@@
# lines it prints. These lock in the behaviour that had (or could regress into)
# the false-"reboot needed" bug.
#
# Usage:  tests/run-tests.sh        # runs all tests, non-zero exit on any failure
set -uo pipefail

ENGINE="$(cd "$(dirname "$0")/.." && pwd)/update_system.sh"
PASS=0 FAIL=0

# --- mock system tools common to every scenario ----------------------------
setup_common() {
    local d="$1"
    cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
# Strip sudo's own options; a bare `sudo -v` (validate) just succeeds. The `-n`
# (non-interactive) scoped probe fails by default -- this mock models a box
# WITHOUT the ONEUP-0023 passwordless drop-in installed, so sudo_init's guard
# falls through to the normal interactive-validate + keep-alive path, same as
# every scenario expected before that guard existed.
for a in "$@"; do [[ "$a" == "-n" ]] && exit 1; done
while [[ $# -gt 0 ]]; do
    case "$1" in
        -A|-v|-k|-E) shift ;;
        -p) shift 2 ;;
        --) shift; break ;;
        -*) shift ;;
        *) break ;;
    esac
done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
    cat > "$d/systemctl" <<'EOF'
#!/usr/bin/env bash
[[ "$1 $2" == "is-active packagekit" ]] && exit 3   # inactive
exit 0
EOF
    cat > "$d/snapper" <<'EOF'
#!/usr/bin/env bash
[[ "$*" == *--print-number* ]] && { echo 42; exit 0; }
[[ "$1" == "--no-headers" ]] && { echo "40 | single"; exit 0; }
exit 0
EOF
    printf '#!/usr/bin/env bash\nexit 0\n' > "$d/notify-send"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$d/flatpak"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$d/fwupdmgr"
    chmod +x "$d"/*
}

# Run the engine with a given mock dir; echo its combined output.
run_engine() {
    local mockdir="$1"; shift
    PATH="$mockdir:$PATH" bash "$ENGINE" "$@" --log="$mockdir/run.log" 2>&1
}

check() {  # name, expected-substring, haystack
    local name="$1" needle="$2" hay="$3"
    if grep -qF -- "$needle" <<<"$hay"; then
        echo "  ok   - $name"; PASS=$((PASS+1))
    else
        echo "  FAIL - $name (missing: $needle)"; FAIL=$((FAIL+1))
    fi
}
check_absent() {  # name, forbidden-substring, haystack
    local name="$1" needle="$2" hay="$3"
    if grep -qF -- "$needle" <<<"$hay"; then
        echo "  FAIL - $name (unexpected: $needle)"; FAIL=$((FAIL+1))
    else
        echo "  ok   - $name"; PASS=$((PASS+1))
    fi
}
check_re() {  # name, extended-regex, haystack
    local name="$1" re="$2" hay="$3"
    if grep -qE -- "$re" <<<"$hay"; then
        echo "  ok   - $name"; PASS=$((PASS+1))
    else
        echo "  FAIL - $name (no match: $re)"; FAIL=$((FAIL+1))
    fi
}

# ---------------------------------------------------------------------------
echo "TEST: up-to-date system does NOT advise a reboot (the original bug)"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)          exit 0 ;;
  *dup*|*update*)     echo "Nothing to do." ; exit 0 ;;
  *needs-rebooting*)  exit 0 ;;            # no reboot required
  *clean*)            exit 0 ;;
  *" lr "*|*" lr -u"*) echo "1 | repo | X | Yes | (r ) | Yes | http://x" ; exit 0 ;;
  *ps*)               exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system,cache)
check         "system reports already up to date" "@@STEP_END@@|system|ok|already up to date" "$out"
check         "reboot marker is NO"               "@@REBOOT@@|no"  "$out"
check_absent  "no false reboot=yes"               "@@REBOOT@@|yes" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: the cache clean reports the disk it reclaimed (@@FREED@@)"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *clean*)           exit 0 ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
# Model the package cache shrinking across the clean: the first du (before)
# reports 2 GiB, the second (after) 1 GiB, so the engine sees an exactly-1-GiB
# delta (numfmt --to=iec rounds, so round values keep the assertion stable).
# du is invoked via `sudo du`, and setup_common's sudo mock execs its args, so
# this mock du (first in PATH) answers both measurements from a call counter.
export MOCK_DUCOUNT="$d/ducount"; rm -f "$MOCK_DUCOUNT"
cat > "$d/du" <<'EOF'
#!/usr/bin/env bash
n=$(cat "$MOCK_DUCOUNT" 2>/dev/null || echo 0)
echo $((n + 1)) > "$MOCK_DUCOUNT"
[[ "$n" -eq 0 ]] && printf '%s\t/var/cache/zypp\n' 2147483648 \
                 || printf '%s\t/var/cache/zypp\n' 1073741824
EOF
chmod +x "$d/zypper" "$d/du"
out=$(run_engine "$d" --steps=cache)
check         "cache emits the FREED marker"      "@@FREED@@|cache|"     "$out"
check         "FREED reports the reclaimed size"  "@@FREED@@|cache|1.0G" "$out"
check         "cache prints a plain reclaimed line" "Reclaimed 1.0G"     "$out"
unset MOCK_DUCOUNT
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: an already-empty cache reclaims nothing and emits no FREED marker"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *clean*)           exit 0 ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
# du reports the same size before and after, so the engine must stay silent
# rather than claim a misleading "Reclaimed 0B".
cat > "$d/du" <<'EOF'
#!/usr/bin/env bash
printf '%s\t/var/cache/zypp\n' 104857600
EOF
chmod +x "$d/zypper" "$d/du"
out=$(run_engine "$d" --steps=cache)
check        "cache step still succeeds"          "@@STEP_END@@|cache|ok" "$out"
check_absent "no FREED marker when nothing freed" "@@FREED@@"             "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: a refresh failure but a successful dup is success, not a failed step"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)         exit 1 ;;                                    # repo refresh FAILS
  *dup*|*update*)    echo "3 packages to upgrade."; exit 0 ;;      # but the upgrade SUCCEEDS
  *needs-rebooting*) exit 0 ;;
  *ps\ -sss*|*"ps -sss"*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check        "dup success recorded ok despite refresh fail" "@@STEP_END@@|system|ok" "$out"
check_absent "not recorded as a failed step"                "@@STEP_END@@|system|fail" "$out"
check        "real change detected (installed, sys_changed)" "@@INSTALLED@@|3|yes" "$out"
check        "stale-metadata note surfaced as a hint"        "@@HINT@@" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: kernel/core change (needs-rebooting=102) DOES advise a reboot"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "The following 5 packages are going to be upgraded:"; echo "5 packages to upgrade."; exit 0 ;;
  *needs-rebooting*) exit 102 ;;           # reboot required
  *ps*)              exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check "reboot advised on kernel change" "@@REBOOT@@|yes" "$out"
# Honesty guard (ONEUP-0019): with no kernel/driver name in the transaction log,
# the reason must fall back to the generic phrase and NOT invent "a new kernel".
check_absent "no false kernel naming without evidence" "@@REBOOT@@|yes|a new kernel" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: reboot advice NAMES the kernel and graphics driver that triggered it (ONEUP-0019)"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)
    cat <<'LOG'
The following 7 packages are going to be upgraded:
  kernel-default kernel-default-devel Mesa Mesa-dri nvidia-video-G06 nvidia-gl-G06 glibc
7 packages to upgrade.
LOG
    exit 0 ;;
  *needs-rebooting*) exit 102 ;;           # reboot required
  *ps*)              exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check "reboot still advised when named"      "@@REBOOT@@|yes"                       "$out"
check "reboot reason names the kernel"       "@@REBOOT@@|yes|a new kernel"          "$out"
check "reboot reason names NVIDIA driver"    "NVIDIA graphics driver"               "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: a FAILED system step does not claim changes / reboot, and gives a hint"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "Download (curl) error 6 - could not resolve host download.opensuse.org"; exit 1 ;;
  *needs-rebooting*) exit 0 ;;
  *ps*)              exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check        "system step marked fail"      "@@STEP_END@@|system|fail" "$out"
check        "network hint emitted"         "@@HINT@@|A download failed" "$out"
check        "no reboot after failure"      "@@REBOOT@@|no"  "$out"
check_absent "no reboot=yes after failure"  "@@REBOOT@@|yes" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: package-only change offers a SERVICE restart, not a reboot"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "3 packages to upgrade."; exit 0 ;;
  *needs-rebooting*) exit 0 ;;             # no kernel/core change
  *ps\ -sss*|*"ps -sss"*) printf 'foo.service\nbar.service\n'; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check        "services listed for restart" "@@SERVICES@@|foo.service bar.service" "$out"
check        "no reboot for package-only"  "@@REBOOT@@|no" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --check reports counts read-only and never installs"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *list-updates* ]]; then
  printf 'S | Repo | Name | Cur | Avail | Arch\n--+--+--+--+--+--\nv | r | a | 1 | 2 | x\nv | r | b | 1 | 2 | x\n'
  exit 0
fi
# Any dup/update/clean during --check would be a bug: fail loudly.
[[ "$*" == *dup* || "$*" == *update* ]] && { echo "BUG: mutated in --check" >&2; exit 99; }
exit 0
EOF
chmod +x "$d/zypper"
cat > "$d/flatpak" <<'EOF'
#!/usr/bin/env bash
[[ "$*" == *--user* ]] && echo "org.x.App 1"
exit 0
EOF
chmod +x "$d/flatpak"
out=$(run_engine "$d" --check --steps=system,flatpak)
check        "system update count = 2"  "@@CHECK@@|system|2" "$out"
check        "total marker present"     "@@CHECK@@|TOTAL"    "$out"
check_absent "no mutation during check" "BUG: mutated"       "$out"
# --check also emits a per-package detail line (name|from|to) for the GUI preview.
check        "system detail item a 1->2" "@@CHECK_ITEM@@|system|a|1|2"       "$out"
check        "system detail item b 1->2" "@@CHECK_ITEM@@|system|b|1|2"       "$out"
check        "flatpak detail item"       "@@CHECK_ITEM@@|flatpak|org.x.App|" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --size=system reports the solver's download size and never really updates"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
# The dry-run reports a size; a real (non-dry-run) transaction would be a bug.
if [[ "$*" == *dup* && "$*" == *--dry-run* ]]; then
  echo "2 packages to upgrade."
  echo "Overall download size: 1.3 GiB. Already cached: 0 B. After the operation, additional 45.0 MiB will be used."
  exit 0
fi
[[ "$*" == *dup* || "$*" == *update* ]] && { echo "BUG: real transaction in --size" >&2; exit 99; }
exit 0
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --size=system)
check        "size marker carries the figure" "@@SIZE@@|system|1.3 GiB" "$out"
check_absent "size mode never really updates"  "BUG: real transaction"  "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
# Current zypper (1.14.98 / libzypp 17.38) renamed the summary line: it prints
# "Package download size:   371.4 MiB" and dropped "Overall download size:" /
# "Already cached:" entirely (verified absent from /usr/bin/zypper's strings).
# The old wording above is kept for Leap's older zypper, so the parse must accept
# BOTH — this test is what the mock's stale wording hid.
echo "TEST: --size=system parses current zypper's 'Package download size' wording"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *dup* && "$*" == *--dry-run* ]]; then
  echo "137 packages to upgrade."
  echo ""
  echo "Package download size:   371.4 MiB"
  echo ""
  echo "Package install size change:"
  echo "              |      1.42 GiB  required by packages that will be installed"
  exit 0
fi
[[ "$*" == *dup* || "$*" == *update* ]] && { echo "BUG: real transaction in --size" >&2; exit 99; }
exit 0
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --size=system)
check        "size marker carries the new-wording figure" "@@SIZE@@|system|371.4 MiB" "$out"
check_absent "new-wording size is not reported as nothing" "nothing to fetch" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
# A failed dry run (cancelled password prompt, held package lock) must NOT be
# reported as a confident "0 B to download" — the same never-claim-what-you-
# didn't-earn rule the step tests enforce. It stays silent on SIZE, hints, and
# exits non-zero so the GUI re-arms its "Show download size" link.
echo "TEST: --size never reports 0 B when the dry run itself failed"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *--dry-run* ]]; then
  echo "sudo: a terminal is required to read the password" >&2
  exit 1
fi
exit 0
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --size=system); rc=$?
check_absent "a failed dry run reports no size at all" "@@SIZE@@" "$out"
check        "a failed dry run hints why"              "@@HINT@@" "$out"
check        "a failed dry run logs what zypper said"  "zypper: sudo: a terminal is required" "$out"
# Exit code asserted inline (the suite's convention — there is no check() for rc).
if [[ $rc -ne 0 ]]; then echo "  ok   - a failed dry run exits non-zero"; PASS=$((PASS+1));
else echo "  FAIL - a failed dry run exits non-zero (rc=$rc)"; FAIL=$((FAIL+1)); fi
rm -rf "$d"

# ---------------------------------------------------------------------------
# The GUI runs this engine through QProcess, so there is NO terminal. sudo can
# only fall back to the graphical password helper if it finds SUDO_ASKPASS in its
# environment, and a privileged call inside `out=$(sudo …)` cannot always see
# sudo_init's cached credential (a subshell changes the parent pid that sudo keys
# its no-tty credential record on). Without the export such a call dies with
# "a terminal is required to read the password" — the ONEUP-0036 bug. This asserts
# the export reaches the privileged commands themselves, not just the -A calls.
echo "TEST: privileged commands can reach the graphical password helper (no tty)"
d=$(mktemp -d); setup_common "$d"
# This sudo mock reports whether SUDO_ASKPASS was exported into its environment.
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
[[ -n "${SUDO_ASKPASS:-}" ]] && echo "ASKPASS-VISIBLE=$SUDO_ASKPASS" >&2 || echo "ASKPASS-MISSING" >&2
for a in "$@"; do [[ "$a" == "-n" ]] && exit 1; done
while [[ $# -gt 0 ]]; do
    case "$1" in
        -A|-v|-k|-E) shift ;;
        -p) shift 2 ;;
        --) shift; break ;;
        -*) shift ;;
        *) break ;;
    esac
done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
printf '#!/usr/bin/env bash\n[[ "$*" == *--dry-run* ]] && { echo "Package download size:   12.5 MiB"; exit 0; }\nexit 0\n' > "$d/zypper"
chmod +x "$d/sudo" "$d/zypper"
out=$(run_engine "$d" --size=system 2>&1)
check        "the askpass helper is exported to privileged commands" "ASKPASS-VISIBLE=" "$out"
check_absent "no privileged command runs without an askpass helper"  "ASKPASS-MISSING" "$out"
check        "the size still parses through the real code path" "@@SIZE@@|system|12.5 MiB" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
# ONEUP-0038: a whole run must cost exactly ONE password prompt. sudo_init obtains
# the credential once, but with no terminal (the GUI runs us through QProcess) the
# cached record is keyed to the PARENT PROCESS ID — sudoers(5) `timestamp_type`,
# whose `tty` default falls back to the ppid when no terminal is present. Measured
# on bash 5.3: `$(cmd)` keeps our own pid as the parent, but `$(cmd | other)`,
# `$( { …; } )` and `$(a; b)` fork a subshell FIRST, so a sudo inside one is
# authenticated *separately* — an extra password popup, in sudo's own bare
# "password for root" wording. A user reported three in a row.
#
# The mock models that cache faithfully — one timestamp file per parent pid — and
# logs a line whenever a call actually has to authenticate, so this counts real
# password popups rather than sudo invocations.
echo "TEST: a full run asks for the password exactly once (no per-step prompts)"
d=$(mktemp -d); setup_common "$d"
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
ts="${ONEUP_TEST_TS:?mock sudo needs ONEUP_TEST_TS}"
for a in "$@"; do [[ "$a" == "-k" ]] && rm -f "$ts/ts.$PPID"; done
for a in "$@"; do [[ "$a" == "-n" ]] && exit 1; done   # no passwordless drop-in
if [[ ! -f "$ts/ts.$PPID" ]]; then
    echo "PROMPT ppid=$PPID cmd=$*" >> "$ts/prompts"
    : > "$ts/ts.$PPID"
fi
while [[ $# -gt 0 ]]; do
    case "$1" in
        -A|-v|-k|-E) shift ;;
        -p) shift 2 ;;
        --) shift; break ;;
        -*) shift ;;
        *) break ;;
    esac
done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)           exit 0 ;;
  *dup*|*update*)      echo "Nothing to do." ; exit 0 ;;
  *needs-rebooting*)   exit 0 ;;
  *clean*)             exit 0 ;;
  *" lr "*|*" lr -u"*) echo "1 | repo | X | Yes | (r ) | Yes | http://x" ; exit 0 ;;
  *packages*)          exit 0 ;;
  *ps*)                exit 0 ;;
  *) exit 0 ;;
esac
EOF
printf '#!/usr/bin/env bash\necho "1024\t/var/cache/zypp"\n' > "$d/du"
chmod +x "$d/sudo" "$d/zypper" "$d/du"
ONEUP_TEST_TS="$d" run_engine "$d" >/dev/null 2>&1
prompts=$(grep -c . "$d/prompts" 2>/dev/null || echo 0)
if [[ "$prompts" == "1" ]]; then
    echo "  ok   - the whole run asks for the password exactly once"; PASS=$((PASS+1))
else
    echo "  FAIL - the whole run asks for the password exactly once (got $prompts)"; FAIL=$((FAIL+1))
    awk '{print "         " $0}' "$d/prompts" 2>/dev/null
fi
rm -rf "$d"

# ---------------------------------------------------------------------------
# ONEUP-0045: a real run records itself so a GUI starting mid-run can find it. Runs
# outlive the window on purpose (ONEUP-0042), so without this the user is offered a Run
# button whose only possible outcome is the package-lock message.
echo "TEST: a real run records itself in a run-state file and clears it on exit"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\ncase "$*" in *dup*|*update*) echo "Nothing to do."; exit 0;; *) exit 0;; esac\n' > "$d/zypper"
# Records the state file's contents while the run is still in flight — it is deleted on
# exit, so a check afterwards could not tell "never written" from "written and cleared".
cat > "$d/snapper" <<EOF
#!/usr/bin/env bash
cp "$d/run.state" "$d/state-during-run" 2>/dev/null
[[ "\$*" == *--print-number* ]] && { echo 42; exit 0; }
[[ "\$1" == "--no-headers" ]] && { echo "40 | single"; exit 0; }
exit 0
EOF
chmod +x "$d/zypper" "$d/snapper"
ONEUP_RUN_STATE="$d/run.state" run_engine "$d" --steps=system >/dev/null 2>&1
check_eq() {  # name, expected, actual
    local name="$1" want="$2" got="$3"
    if [[ "$got" == "$want" ]]; then
        echo "  ok   - $name"; PASS=$((PASS+1))
    else
        echo "  FAIL - $name (want '$want', got '$got')"; FAIL=$((FAIL+1))
    fi
}
if [[ -f "$d/state-during-run" ]]; then
    echo "  ok   - the run is recorded while it is in flight"; PASS=$((PASS+1))
    mapfile -t st < "$d/state-during-run"
    if [[ "${st[0]:-}" =~ ^[0-9]+$ ]]; then
        echo "  ok   - it records the engine's pid"; PASS=$((PASS+1))
    else
        echo "  FAIL - it records the engine's pid (got '${st[0]:-}')"; FAIL=$((FAIL+1))
    fi
    if [[ "${st[1]:-}" == *"$d"* ]]; then
        echo "  ok   - it records the log path to follow"; PASS=$((PASS+1))
    else
        echo "  FAIL - it records the log path (got '${st[1]:-}')"; FAIL=$((FAIL+1))
    fi
    check_eq "it records which steps are running" "system" "${st[2]:-}"
else
    # +4: this check plus the three field checks that could not run.
    echo "  FAIL - no run-state file was written during the run"; FAIL=$((FAIL+4))
fi
if [[ ! -f "$d/run.state" ]]; then
    echo "  ok   - the record is cleared when the run ends"; PASS=$((PASS+1))
else
    echo "  FAIL - a finished run left its record behind"; FAIL=$((FAIL+1))
fi
rm -rf "$d"

echo "TEST: a read-only --check run does NOT touch the run-state file"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\nexit 0\n' > "$d/zypper"; chmod +x "$d/zypper"
echo "pretend-a-real-run-is-in-flight" > "$d/run.state"
ONEUP_RUN_STATE="$d/run.state" run_engine "$d" --check >/dev/null 2>&1
if [[ -f "$d/run.state" ]] && grep -q pretend "$d/run.state"; then
    echo "  ok   - --check leaves a real run's record alone"; PASS=$((PASS+1))
else
    echo "  FAIL - --check erased a real run's record"; FAIL=$((FAIL+1))
fi
rm -rf "$d"

# ---------------------------------------------------------------------------
# ONEUP-0043: an orphaned password dialog must not be left on the user's screen. Eleven
# had accumulated on the reporter's machine, and one was still open 5.7 hours after its
# run had finished — a dialog whose sudo has exited is one nobody is waiting on, and a
# pile of unexplained password boxes is exactly what makes an updater feel untrustworthy.
echo "TEST: an orphaned password dialog is reaped when the run ends"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\nexit 0\n' > "$d/zypper"
# Stands in for ksshaskpass: sleeps like a dialog waiting for input.
printf '#!/usr/bin/env bash\nsleep 300\n' > "$d/mock-askpass"
chmod +x "$d/zypper" "$d/mock-askpass"
# Orphan: no sudo anywhere in its ancestry, which is the "nothing is waiting on this"
# state the reap targets. (Deliberately not tested via pid 1 — under systemd a user
# session's orphans are reparented to `systemd --user`, so a pid-1 check never fires.)
setsid "$d/mock-askpass" "System Updater: authenticate to update the system" \
    >/dev/null 2>&1 &
orphan_pid=$!
# Live: a dialog whose parent IS a waiting sudo must survive — killing one would break a
# concurrent OneUp process mid-authentication. fake-sudo stands in for that parent (the
# reap matches on the parent's command line, and "fake-sudo" contains "sudo").
cat > "$d/fake-sudo" <<EOF
#!/usr/bin/env bash
"$d/mock-askpass" "\$@" &
wait
EOF
chmod +x "$d/fake-sudo"
"$d/fake-sudo" "System Updater: authenticate to update the system" >/dev/null 2>&1 &
live_parent=$!
sleep 0.5
live_pid=$(pgrep -P "$live_parent" -f mock-askpass | head -1)
if ! kill -0 "$orphan_pid" 2>/dev/null || [[ -z "$live_pid" ]]; then
    echo "  SKIP - could not stage the dialogs (orphan=$orphan_pid live=${live_pid:-none})"
else
    ONEUP_ASKPASS="$d/mock-askpass" run_engine "$d" --steps=cache >/dev/null 2>&1
    reaped=no
    for _ in $(seq 1 20); do
        kill -0 "$orphan_pid" 2>/dev/null || { reaped=yes; break; }
        sleep 0.1
    done
    if [[ "$reaped" == yes ]]; then
        echo "  ok   - the orphaned dialog is closed when the run ends"; PASS=$((PASS+1))
    else
        echo "  FAIL - an orphaned password dialog was left on screen"; FAIL=$((FAIL+1))
    fi
    if kill -0 "$live_pid" 2>/dev/null; then
        echo "  ok   - a dialog someone is still waiting on is left alone"; PASS=$((PASS+1))
    else
        echo "  FAIL - killed a live dialog another process was waiting on"; FAIL=$((FAIL+1))
    fi
fi
kill -9 "$orphan_pid" "$live_parent" ${live_pid:+"$live_pid"} 2>/dev/null
wait "$live_parent" 2>/dev/null
rm -rf "$d"

# ---------------------------------------------------------------------------
# ONEUP-0042: the GUI going away mid-run must not abandon the transaction. Our stdout
# is a pipe to the GUI; when the user quits, a plain `tee` dies on the broken pipe and
# the engine is then SIGPIPEd on its next line — killed without running cleanup. That
# is what happened to a real run: zypper was left orphaned mid-transaction (a
# half-applied rpm transaction can leave packages broken) and its abandoned lock
# blocked the next two runs. `head -c` below closes the pipe early, standing in for the
# GUI quitting; the run must still reach its end and finish writing the log.
echo "TEST: a run survives the GUI going away and still finishes (broken stdout pipe)"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *dup*|*update*)
    # Enough output to be sure the reader is gone before the run ends.
    for i in $(seq 1 200); do echo "Preloading: package-$i.rpm [done]"; done
    exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
PATH="$d:$PATH" bash "$ENGINE" --steps=system --log="$d/run.log" 2>&1 | head -c 200 >/dev/null
# The engine keeps running after the reader closes; wait for the log to settle.
for _ in $(seq 1 50); do grep -q '@@DONE@@' "$d/run.log" 2>/dev/null && break; sleep 0.1; done
out=$(cat "$d/run.log" 2>/dev/null)
check "the run reaches its end despite the closed pipe" "@@DONE@@" "$out"
check "the summary still lands in the log"              "Summary" "$out"
check "the step still completes"                        "@@STEP_END@@|system" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
# ONEUP-0040: a long download must never look like a hang. The zypper output below
# is copied verbatim from a real Tumbleweed upgrade log, including the padded
# counter ("( 1/3)") and the preload phase, which carries no counter at all.
echo "TEST: the engine reports per-package progress during download and install"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*) exit 0 ;;
  *dup*|*update*)
    echo "3 packages to upgrade."
    echo "Preloading Packages [..."
    echo "Preloading: libglfw3-3.4-67.34.x86_64.rpm [done]"
    echo "Preloading: libbox2d2-2.4.1-18.53.x86_64.rpm [done]"
    echo "Retrieving: cpupower-lang-7.1.4-17.d_t.142.noarch (devel-tools) (1/3),  31.0 KiB"
    echo "Retrieving: libcapstone5-5.0.6-18.d_t.5.x86_64 (devel-tools) (2/3), 898.3 KiB"
    echo "Checking for file conflicts: [.........done]"
    echo "( 1/3) Installing: cpupower-lang-7.1.4-17.d_t.142.noarch [...done]"
    echo "( 3/3) Installing: libcapstone5-5.0.6-18.d_t.5.x86_64 [..done]"
    exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system 2>&1)
check "the preload phase reports a running count (zypper gives no total there)" \
      "@@PROGRESS@@|system|2|0|download" "$out"
check "a counted download reports done and total" "@@PROGRESS@@|system|2|3|download" "$out"
check "the install phase reports done and total"  "@@PROGRESS@@|system|1|3|install" "$out"
check "zypper's padded counter is parsed"         "@@PROGRESS@@|system|3|3|install" "$out"
check_absent "a non-package line emits no progress" "@@PROGRESS@@|system|0|" "$out"
# The filter is a pass-through: losing zypper's own words would blind the log.
check "zypper's own output still reaches the log" "Checking for file conflicts" "$out"
check "the step still succeeds through the filter" "@@STEP_END@@|system|ok" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
# ONEUP-0047: a stop must be honoured only at a safe boundary. Interrupting rpm can leave
# programs half-installed, and signalling the engine mid-transaction would orphan a zypper
# that carries on anyway — the failure mode this project takes most seriously.
echo "TEST: a stop skips the remaining steps, reports 'stopped', and still summarises"
d=$(mktemp -d); setup_common "$d"
# The FIRST step requests the stop, so every later step must be skipped. Asking before
# the run started would be a leftover request and is deliberately ignored (see the stale
# test below), so the request has to be made from inside the run.
cat > "$d/zypper" <<EOF
#!/usr/bin/env bash
case "\$*" in
  *refresh*) touch "$d/stop.request"; exit 0 ;;
  *dup*|*update*) echo "Nothing to do."; exit 0 ;;
  *clean*) echo "CACHE-CLEAN-RAN"; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(ONEUP_STOP_FILE="$d/stop.request" run_engine "$d" --steps=system,flatpak,cache 2>&1)
check        "the run reports it stopped, not that it succeeded" "@@DONE@@|stopped" "$out"
check_absent "a stopped run never claims success" "@@DONE@@|ok" "$out"
check_absent "steps after the stop do not run" "CACHE-CLEAN-RAN" "$out"
check_absent "no later step is even begun" "@@STEP_BEGIN@@|cache" "$out"
check        "the summary is still printed" "Summary" "$out"
check "the hint says an install is never cut half-way" \
      "never interrupts an install half-way" "$out"
check "stopping before the transaction is recorded honestly" \
      "@@STEP_END@@|system|skip|stopped before installing anything" "$out"
rm -rf "$d"

echo "TEST: a stop DURING the run lets the running transaction finish, then stops"
d=$(mktemp -d); setup_common "$d"
# The transaction requests the stop itself, mid-flight — the engine must still see it
# through and only then skip the remaining steps.
cat > "$d/zypper" <<EOF
#!/usr/bin/env bash
case "\$*" in
  *refresh*) exit 0 ;;
  *dup*|*update*)
      touch "$d/stop.request"          # user hits Stop while the install is running
      echo "( 1/1) Installing: demo-1.0.x86_64 [...done]"
      echo "1 packages to upgrade."
      exit 0 ;;
  *clean*) echo "CACHE-CLEAN-RAN"; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(ONEUP_STOP_FILE="$d/stop.request" run_engine "$d" --steps=system,cache 2>&1)
check        "the transaction that was already running completes" "@@STEP_END@@|system|ok" "$out"
check        "progress from that transaction is still reported" "@@PROGRESS@@|system|1|1|install" "$out"
check_absent "the step after the stop does not run" "CACHE-CLEAN-RAN" "$out"
check        "the run reports stopped" "@@DONE@@|stopped" "$out"
rm -rf "$d"

echo "TEST: a stop left over from a previous run does not abort the next one"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\ncase "$*" in *dup*|*update*) echo "Nothing to do."; exit 0;; *) exit 0;; esac\n' > "$d/zypper"
chmod +x "$d/zypper"
# Older than the run, so it must be ignored rather than silently aborting the run.
touch -d '1 hour ago' "$d/stale-stop"
out=$(ONEUP_STOP_FILE="$d/stale-stop" run_engine "$d" --steps=system 2>&1)
check        "a stale stop request is cleared, so the run proceeds" "@@STEP_BEGIN@@|system" "$out"
check_absent "the run is not reported as stopped" "@@DONE@@|stopped" "$out"
if [[ ! -f "$d/stale-stop" ]]; then
    echo "  ok   - the stop request is removed on exit"; PASS=$((PASS+1))
else
    echo "  FAIL - the stop request was left behind"; FAIL=$((FAIL+1))
fi
rm -rf "$d"

# ONEUP-0046: the progress parser reads zypper's own wording, so an upstream rename makes
# it silently stop. Silence is exactly how the "download size: 0 B" bug hid for weeks
# (ONEUP-0035). A transaction that installed packages but produced no progress must say so.
echo "TEST: a transaction with no recognisable progress lines says so (stale-parser canary)"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*) exit 0 ;;
  *dup*|*update*)
    echo "3 packages to upgrade."
    # Plausible future wording that today's parser does NOT recognise.
    echo "Prefetching: libglfw3-3.4-67.34.x86_64.rpm [done]"
    echo "[1 of 3] Unpacking: libglfw3-3.4-67.34.x86_64"
    exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system 2>&1)
check_absent "no progress markers are invented from unknown wording" "@@PROGRESS@@" "$out"
check "the run warns that progress could not be followed" \
      "zypper has probably renamed the lines it reports progress on" "$out"
check "the step still succeeds — the update itself was fine" "@@STEP_END@@|system|ok" "$out"
rm -rf "$d"

echo "TEST: recognised progress lines raise NO stale-parser warning"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*) exit 0 ;;
  *dup*|*update*)
    echo "3 packages to upgrade."
    echo "( 1/3) Installing: libglfw3-3.4-67.34.x86_64 [...done]"
    exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system 2>&1)
check        "progress is reported" "@@PROGRESS@@|system|1|3|install" "$out"
check_absent "no false stale-parser warning" "probably renamed the lines" "$out"
rm -rf "$d"

echo "TEST: progress parsing does not cost an extra password prompt"
d=$(mktemp -d); setup_common "$d"
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
ts="${ONEUP_TEST_TS:?mock sudo needs ONEUP_TEST_TS}"
for a in "$@"; do [[ "$a" == "-k" ]] && rm -f "$ts/ts.$PPID"; done
for a in "$@"; do [[ "$a" == "-n" ]] && exit 1; done
if [[ ! -f "$ts/ts.$PPID" ]]; then
    echo "PROMPT ppid=$PPID cmd=$*" >> "$ts/prompts"
    : > "$ts/ts.$PPID"
fi
while [[ $# -gt 0 ]]; do
    case "$1" in
        -A|-v|-k|-E) shift ;;
        -p) shift 2 ;;
        --) shift; break ;;
        -*) shift ;;
        *) break ;;
    esac
done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
printf '#!/usr/bin/env bash\ncase "$*" in *dup*|*update*) echo "Preloading: a.rpm [done]"; exit 0;; *) exit 0;; esac\n' > "$d/zypper"
chmod +x "$d/sudo" "$d/zypper"
ONEUP_TEST_TS="$d" run_engine "$d" --steps=system >/dev/null 2>&1
prompts=$(grep -c . "$d/prompts" 2>/dev/null || echo 0)
if [[ "$prompts" == "1" ]]; then
    echo "  ok   - the extra pipeline stage keeps sudo in this shell (one prompt)"; PASS=$((PASS+1))
else
    echo "  FAIL - the extra pipeline stage keeps sudo in this shell (got $prompts)"; FAIL=$((FAIL+1))
fi
rm -rf "$d"

# ---------------------------------------------------------------------------
# ONEUP-0039: when another program holds the package lock, every zypper step fails
# for that one reason. A user quit OneUp mid-download; the engine's zypper kept
# installing in the background (by design — killing a transaction half-way can break
# the package database), so the next run showed zypper's own words twice
# ("System management is locked by the application with pid 447150 (zypper)") and
# reported failures for steps whose only problem was "OneUp is already busy".
echo "TEST: another program holding the package lock is named, not just failed through"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\nexit 0\n' > "$d/zypper"; chmod +x "$d/zypper"
# $$ is this test shell — a live pid whose /proc entry exists, standing in for the
# foreign zypper. Its /proc/<pid>/comm supplies the name the engine reports.
echo "$$" > "$d/zypp.pid"
out=$(ONEUP_ZYPP_PID_FILE="$d/zypp.pid" run_engine "$d" 2>&1); rc=$?
check_re     "the busy program is named with its pid" "package manager is busy: .* \(process $$\)" "$out"
check        "the hint explains it is often OneUp's own earlier run" \
             "still finishing in the background" "$out"
check_absent "no snapshot is taken when nothing can change" "@@SNAPSHOT@@" "$out"
check_absent "no step is even begun"                        "@@STEP_BEGIN@@" "$out"
if [[ $rc -ne 0 ]]; then echo "  ok   - a blocked run exits non-zero"; PASS=$((PASS+1));
else echo "  FAIL - a blocked run exits non-zero (rc=$rc)"; FAIL=$((FAIL+1)); fi
rm -rf "$d"

echo "TEST: a stale lock file (holder already gone) does NOT block a run"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *dup*|*update*) echo "Nothing to do." ; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
# A pid that cannot be running: zypper leaves the file behind when it is killed, and
# it clears the entry itself — a dead pid must never block the next run.
dead=999999; while [[ -d "/proc/$dead" ]]; do dead=$((dead+1)); done
echo "$dead" > "$d/zypp.pid"
out=$(ONEUP_ZYPP_PID_FILE="$d/zypp.pid" run_engine "$d" --steps=system 2>&1)
check_absent "a stale lock does not block the run" "package manager is busy" "$out"
check        "the system step still runs"          "@@STEP_BEGIN@@|system" "$out"
rm -rf "$d"

echo "TEST: a Flatpak-only run ignores the zypper lock (it doesn't use zypper)"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\nexit 0\n' > "$d/zypper"; chmod +x "$d/zypper"
echo "$$" > "$d/zypp.pid"
out=$(ONEUP_ZYPP_PID_FILE="$d/zypp.pid" run_engine "$d" --steps=flatpak 2>&1)
check_absent "a Flatpak-only run is not blocked" "package manager is busy" "$out"
check        "the Flatpak step still runs"       "@@STEP_BEGIN@@|flatpak" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
# zypper exit 7 = ZYPP_LOCKED ("the ZYPP library is locked, e.g. packagekit is
# running"). The hint must name that cause, not guess at authentication.
echo "TEST: --size names a locked package manager as the reason (zypper exit 7)"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *--dry-run* ]]; then
  echo "System management is locked by the application with pid 4242 (zypper)." >&2
  exit 7
fi
exit 0
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --size=system)
check        "a locked package manager is named as the cause" "another program is using the package manager" "$out"
check_absent "a locked package manager reports no size"       "@@SIZE@@" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
# zypper's 100-103 exits are INFORMATIONAL (update/reboot/restart needed), not
# failures — a nothing-to-fetch answer under one of them is still trustworthy.
echo "TEST: --size treats zypper's informational exit codes as success"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\n[[ "$*" == *--dry-run* ]] && { echo "Nothing to do."; exit 103; }\nexit 0\n' > "$d/zypper"
chmod +x "$d/zypper"
out=$(run_engine "$d" --size=system)
check "informational exit still reports 0 B" "@@SIZE@@|system|0 B" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --size with nothing to fetch reports 0 B (a definite answer, not a failure)"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\n[[ "$*" == *--dry-run* ]] && { echo "Nothing to do."; exit 0; }\nexit 0\n' > "$d/zypper"
chmod +x "$d/zypper"
out=$(run_engine "$d" --size=system)
check "no-op size reports 0 B" "@@SIZE@@|system|0 B" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --grant-auth installs a scoped, password-free sudoers drop-in (stores no password)"
d=$(mktemp -d); setup_common "$d"
# The status probe runs `zypper --version`; keep other calls quiet.
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "--version" ]] && { echo "zypper 1.14.0"; exit 0; }
exit 0
EOF
# Engine validates the rule with `visudo -cf` before installing; accept iff it
# carries our NOPASSWD alias (so a malformed rule would be rejected, as on a real box).
cat > "$d/visudo" <<'EOF'
#!/usr/bin/env bash
f="${!#}"; grep -q "NOPASSWD:" "$f" && exit 0 || exit 1
EOF
# `sudo install -o root -g root -m 0440 src dst` — we aren't root in the test, so
# drop the ownership/mode flags and just copy src→dst.
cat > "$d/install" <<'EOF'
#!/usr/bin/env bash
args=(); while [[ $# -gt 0 ]]; do case "$1" in -o|-g|-m) shift 2;; *) args+=("$1"); shift;; esac; done
cp "${args[0]}" "${args[1]}"
EOF
chmod +x "$d/zypper" "$d/visudo" "$d/install"
authfile="$d/oneup-sudoers"
out=$(ONEUP_AUTH_FILE="$authfile" run_engine "$d" --grant-auth)
rule=$(cat "$authfile" 2>/dev/null)
check "grant reports authorization on"                    "@@AUTH@@|on"      "$out"
check "drop-in is password-free (NOPASSWD)"               "NOPASSWD:"        "$rule"
check "drop-in scopes zypper"                             "$d/zypper"        "$rule"
check "drop-in scopes only 'systemctl stop packagekit'"  "stop packagekit"  "$rule"
check "drop-in covers the 'env LC_ALL=C zypper' wrapper"  "LC_ALL=C zypper"  "$rule"
# Bonus: if a real visudo is on the box, prove the generated rule is truly valid
# (not just accepted by the mock). Absolute paths dodge the mock visudo in $PATH.
# Skipped silently where visudo isn't installed.
realvisudo=""; for c in /usr/sbin/visudo /sbin/visudo /usr/bin/visudo; do [[ -x "$c" ]] && { realvisudo="$c"; break; }; done
if [[ -n "$realvisudo" ]]; then
    if "$realvisudo" -cf "$authfile" >/dev/null 2>&1; then
        echo "  ok   - generated drop-in passes real visudo -cf"; PASS=$((PASS+1))
    else
        echo "  FAIL - generated drop-in rejected by real visudo -cf"; FAIL=$((FAIL+1))
    fi
fi
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --revoke-auth removes the drop-in and reports off"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\nexit 0\n' > "$d/zypper"; chmod +x "$d/zypper"
authfile="$d/oneup-sudoers"; printf 'placeholder\n' > "$authfile"
out=$(ONEUP_AUTH_FILE="$authfile" run_engine "$d" --revoke-auth)
check "revoke reports authorization off" "@@AUTH@@|off" "$out"
if [[ -e "$authfile" ]]; then
    echo "  FAIL - revoke left the drop-in behind"; FAIL=$((FAIL+1))
else
    echo "  ok   - revoke deleted the drop-in"; PASS=$((PASS+1))
fi
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --auth-status reflects the drop-in and can't be fooled by a cached credential"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "--version" ]] && { echo v; exit 0; }
exit 0
EOF
chmod +x "$d/zypper"
# A drop-in-aware sudo: `-n` (non-interactive) succeeds only when the drop-in exists,
# modelling a real NOPASSWD rule — so the probe reads the true state, not the cache.
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
nonint=false
while [[ $# -gt 0 ]]; do case "$1" in -n) nonint=true; shift;; -A|-v|-k|-E) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
if $nonint && [[ -n "${ONEUP_AUTH_FILE:-}" && ! -e "$ONEUP_AUTH_FILE" ]]; then
    echo "sudo: a password is required" >&2; exit 1
fi
exec "$@"
EOF
chmod +x "$d/sudo"
authfile="$d/oneup-sudoers"
out=$(ONEUP_AUTH_FILE="$authfile" run_engine "$d" --auth-status)
check "status is off when no drop-in exists" "@@AUTH@@|off" "$out"
printf 'placeholder\n' > "$authfile"
out=$(ONEUP_AUTH_FILE="$authfile" run_engine "$d" --auth-status)
check "status is on when the drop-in exists" "@@AUTH@@|on" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: with the passwordless drop-in active, a full run skips the interactive sudo -v"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "--version" ]] && { echo v; exit 0; }
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "Nothing to do."; exit 0 ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
# Drop-in ACTIVE: the scoped `-n` probe succeeds, so the engine must NOT reach the
# interactive `sudo -A … -v`. The mock aborts loudly (exit 99) if `-A` is ever passed.
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
for a in "$@"; do [[ "$a" == "-A" ]] && { echo "BUG: interactive sudo -A invoked" >&2; exit 99; }; done
while [[ $# -gt 0 ]]; do case "$1" in -n|-v|-k|-E) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
chmod +x "$d/sudo"
out=$(run_engine "$d" --steps=system,cache)
check_absent "drop-in active: no interactive sudo -A -v" "BUG: interactive sudo -A invoked" "$out"

# Drop-in ABSENT: the scoped `-n` probe fails, so the engine still performs the ONE
# interactive validate exactly as today (marker printed by the mock when `-A` is seen).
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
nonint=false; interactive=false
for a in "$@"; do [[ "$a" == "-n" ]] && nonint=true; [[ "$a" == "-A" ]] && interactive=true; done
$nonint && exit 1                         # scoped probe fails -> drop-in absent
$interactive && echo "INTERACTIVE_VALIDATE_RAN"
while [[ $# -gt 0 ]]; do case "$1" in -n|-v|-k|-E) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
chmod +x "$d/sudo"
out=$(run_engine "$d" --steps=system,cache)
check "drop-in absent: still performs the interactive validate" "INTERACTIVE_VALIDATE_RAN" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: a FAILED firmware update is reported as fail, not success, and does NOT reboot"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in *needs-rebooting*) exit 0 ;; *) exit 0 ;; esac
EOF
cat > "$d/fwupdmgr" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  refresh)     exit 0 ;;
  get-updates) exit 0 ;;   # updates ARE available...
  update)      exit 1 ;;   # ...but the flash fails (device unplugged / ESP unmounted)
  *)           exit 0 ;;
esac
EOF
chmod +x "$d/zypper" "$d/fwupdmgr"
out=$(run_engine "$d" --steps=firmware)
check        "firmware failure marked fail"     "@@STEP_END@@|firmware|fail" "$out"
check        "no reboot after firmware failure" "@@REBOOT@@|no"  "$out"
check_absent "no false reboot on fw failure"    "@@REBOOT@@|yes" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: a SUCCESSFUL firmware update advises a reboot"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in *needs-rebooting*) exit 0 ;; *) exit 0 ;; esac
EOF
cat > "$d/fwupdmgr" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  refresh)     exit 0 ;;
  get-updates) exit 0 ;;
  update)      exit 0 ;;   # flash succeeds
  *)           exit 0 ;;
esac
EOF
chmod +x "$d/zypper" "$d/fwupdmgr"
out=$(run_engine "$d" --steps=firmware)
check "firmware success marked ok"    "@@STEP_END@@|firmware|ok" "$out"
check "reboot advised after firmware" "@@REBOOT@@|yes" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: a failed early step still lets a later step run; the run ends in errors"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "Download (curl) error - could not resolve host"; exit 1 ;;
  *needs-rebooting*) exit 0 ;;
  *clean*)           exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system,cache)
check "system step failed"         "@@STEP_END@@|system|fail" "$out"
check "cache step still ran after" "@@STEP_END@@|cache|ok"    "$out"
check "run reports errors overall" "@@DONE@@|errors"          "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: a non-English locale still detects an up-to-date system (LC_ALL pinned)"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*) exit 0 ;;
  *dup*|*update*)
    # Real zypper translates this line; the engine must pin LC_ALL=C so parsing stays reliable.
    if [[ "$LC_ALL" == "C" ]]; then echo "Nothing to do."; else echo "Nichts zu tun."; fi
    exit 0 ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check        "up-to-date detected under non-English locale" "@@STEP_END@@|system|ok|already up to date" "$out"
check_absent "no false 'packages updated' claim"            "@@STEP_END@@|system|ok|packages updated"   "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: empty or unknown --steps is rejected, not silently reported as a clean run"
d=$(mktemp -d); setup_common "$d"
printf '#!/usr/bin/env bash\nexit 0\n' > "$d/zypper"; chmod +x "$d/zypper"
# Assert the exact exit 2, not merely "non-zero": a bare `set -u` abort exits 1
# before the guard runs, which still passes a -ne 0 check but suppresses the
# helpful message. Pin exit == 2 AND the message so that regression is caught.
out_empty=$(run_engine "$d" --steps=      2>&1); rc_empty=$?
out_bogus=$(run_engine "$d" --steps=bogus 2>&1); rc_bogus=$?
if [[ $rc_empty -eq 2 ]]; then echo "  ok   - empty --steps exits 2"; PASS=$((PASS+1));
else echo "  FAIL - empty --steps exits 2 (rc=$rc_empty)"; FAIL=$((FAIL+1)); fi
if [[ $rc_bogus -eq 2 ]]; then echo "  ok   - unknown --steps exits 2"; PASS=$((PASS+1));
else echo "  FAIL - unknown --steps exits 2 (rc=$rc_bogus)"; FAIL=$((FAIL+1)); fi
check "empty --steps explains the rejection"   "No valid update steps selected" "$out_empty"
check "unknown --steps explains the rejection" "No valid update steps selected" "$out_bogus"
check_absent "no @@DONE@@|ok on an empty step set" "@@DONE@@|ok" "$out_bogus"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: needs-rebooting returning a NON-102 non-zero (e.g. lock held) does NOT advise reboot"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "3 packages to upgrade."; exit 0 ;;
  *needs-rebooting*) exit 7 ;;   # a different failure (e.g. lock held), NOT 102
  *ps\ -sss*|*"ps -sss"*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check        "no reboot on non-102 needs-rebooting" "@@REBOOT@@|no"  "$out"
check_absent "no false reboot=yes on non-102"       "@@REBOOT@@|yes" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: orphans step removes unneeded packages and reports the count"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *packages*--unneeded*) printf 'S|Repo|Name|Ver|Arch\n-+-+-+-+-\ni|r|foo|1|x\ni|r|bar|1|x\n'; exit 0 ;;
  *packages*--orphaned*) exit 0 ;;
  *remove*)              exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=orphans)
check "orphan autoremove reports count" "@@STEP_END@@|orphans|ok|removed 2 package(s)" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: a FAILED orphan removal is marked fail, not success (it deletes packages)"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *packages*--unneeded*) printf 'S|Repo|Name|Ver|Arch\n-+-+-+-+-\ni|r|foo|1|x\n'; exit 0 ;;
  *packages*--orphaned*) exit 0 ;;
  *remove*)              echo "removal failed"; exit 1 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=orphans)
check "failed orphan removal marked fail" "@@STEP_END@@|orphans|fail" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: flatpak reports how many apps were updated"
d=$(mktemp -d); setup_common "$d"
cat > "$d/flatpak" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *remote-ls*--updates*--user*)   printf 'org.x.App\norg.y.App\n'; exit 0 ;;  # 2 user
  *remote-ls*--updates*--system*) printf 'org.z.App\n'; exit 0 ;;             # 1 system
  *) exit 0 ;;                                                                # update/uninstall
esac
EOF
chmod +x "$d/flatpak"
out=$(run_engine "$d" --steps=flatpak)
check "flatpak reports updated count" "@@STEP_END@@|flatpak|ok|3 app(s) updated" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: flatpak with nothing to update reports 'up to date'"
d=$(mktemp -d); setup_common "$d"   # its flatpak mock prints nothing -> 0 updates
out=$(run_engine "$d" --steps=flatpak)
check "flatpak up to date when no updates" "@@STEP_END@@|flatpak|ok|up to date" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --check performs NO privileged auth (never invokes sudo)"
d=$(mktemp -d); setup_common "$d"
# A sudo mock that fails loudly if called at all: --check must be root-free.
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
echo "BUG: sudo invoked during --check" >&2
exit 99
EOF
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
[[ "$*" == *list-updates* ]] && { printf 'S|R|N|C|A|X\nv|r|a|1|2|x\n'; exit 0; }
exit 0
EOF
chmod +x "$d/sudo" "$d/zypper"
out=$(run_engine "$d" --check --steps=system,orphans,cache)
check_absent "check mode never calls sudo"   "BUG: sudo invoked" "$out"
check_absent "check mode records no auth fail" "Authentication failed" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: the sudo keep-alive leaves no orphaned process when a run ends"
d=$(mktemp -d); setup_common "$d"
# A dup that takes ~1s so the keep-alive is mid `sleep 50` when the run finishes
# and cleanup fires — the exact moment a plain `kill <subshell>` (rather than a
# process-group kill) would orphan the sleep, reparented to init for up to 50s.
printf '#!/usr/bin/env bash\ncase "$*" in *refresh*) exit 0;; *dup*|*update*) sleep 1; exit 0;; *) exit 0;; esac\n' > "$d/zypper"
chmod +x "$d/zypper"
# Diff the keep-alive LOOP SHELLS (tagged oneup-keepalive in $0) across the run:
# a survivor is an orphan cleanup failed to reap. Deliberately NOT `pgrep -xf 'sleep
# 50'`: the loop spawns a fresh sleep every 50s, so ANY keep-alive already leaked on
# the machine — including one left by a real interrupted run — made this test fail
# roughly one run in six with a pid that had nothing to do with the run under test.
# The loop shell's pid is stable for the life of the run, so this can't false-positive.
ka_before=$(pgrep -f oneup-keepalive | sort)
run_engine "$d" --steps=system >/dev/null 2>&1
# The process-group kill is asynchronous, so poll rather than guessing a fixed delay.
ka_leaked=""
for _ in $(seq 1 40); do          # up to 4s, returns as soon as it is clean
    ka_after=$(pgrep -f oneup-keepalive | sort)
    ka_leaked=$(comm -13 <(echo "$ka_before") <(echo "$ka_after") | grep -v '^$' || true)
    [[ -z "$ka_leaked" ]] && break
    sleep 0.1
done
if [[ -z "$ka_leaked" ]]; then
    echo "  ok   - no orphaned keep-alive after the run"; PASS=$((PASS+1))
else
    echo "  FAIL - keep-alive orphaned a process: $ka_leaked"; FAIL=$((FAIL+1))
    echo "$ka_leaked" | xargs -r kill 2>/dev/null
fi
rm -rf "$d"

# ---------------------------------------------------------------------------
# ONEUP-0041: cleanup's trap cannot run when the engine is SIGKILLed, and the
# keep-alive used to loop forever in that case. Two were found on the reporter's
# machine still validating sudo every 50 seconds, 40 minutes after the runs that
# spawned them had been killed. So the loop must also watch the engine's pid and
# exit on its own. This asserts the guard directly: run the real loop against a pid
# that is already gone and it must exit rather than idle.
echo "TEST: the keep-alive exits on its own once the engine is gone (SIGKILL-proof)"
dead=999999; while [[ -d "/proc/$dead" ]]; do dead=$((dead+1)); done
ka_body=$(sed -n '/setsid bash -c ./,/oneup-keepalive/p' "$ENGINE")
if [[ -z "$ka_body" ]]; then
    echo "  FAIL - could not find the keep-alive loop in the engine"; FAIL=$((FAIL+1))
else
    # Run the engine's own loop body, substituting a 0.1s sleep for its 50s one so the
    # test doesn't wait a minute to observe the guard. The `kill -0` guard is verbatim.
    loop=$(sed 's/sleep 50/sleep 0.1/' <<<"$ka_body" \
           | sed -e 's/^ *setsid bash -c .//' -e "s/. oneup-keepalive .*$//")
    if timeout 5 bash -c "$loop" oneup-keepalive-test "$dead" >/dev/null 2>&1; then
        echo "  ok   - the keep-alive exits when its engine no longer exists"; PASS=$((PASS+1))
    else
        echo "  FAIL - the keep-alive kept running with no engine to keep alive"; FAIL=$((FAIL+1))
    fi
fi

# ---------------------------------------------------------------------------
echo "TEST: @@INSTALLED@@ keeps its positional 3-field layout the GUI depends on"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "2 packages to upgrade."; exit 0 ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
# count | sys_changed(yes/no) | fw_changed(yes/no)
check_re "INSTALLED marker has count|yes-no|yes-no" \
         '@@INSTALLED@@\|[0-9]+\|(yes|no)\|(yes|no)$' "$out"
check_re "TIMING marker emitted with a numeric duration" \
         '@@TIMING@@\|system\|[0-9]+$' "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: a duplicate repository URL is named in the @@REPO@@ marker"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"lr -u"*)         printf '# | Alias | Name | Enabled | GPG | Refresh | URI\n1 | a | A | Yes | Yes | Yes | http://x.example/repo\n2 | b | B | Yes | Yes | Yes | http://x.example/repo\n'; exit 0 ;;
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "Nothing to do."; exit 0 ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check "REPO marker names the duplicate URL" \
      "@@REPO@@|warn|duplicate|http://x.example/repo" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: a strict run offers the key-import remedy (does NOT import keys on its own)"
d=$(mktemp -d); setup_common "$d"
# A plain run must never pass --gpg-auto-import-keys; if it does, that's the bug
# (silently trusting a new key). The upgrade fails on the rejected signing key.
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *gpg-auto-import-keys*) echo "BUG: imported keys without opt-in" >&2; exit 88 ;;
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "Signature verification failed for repository 'oss' (key expired)"; exit 1 ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system,cache)
check_absent "strict run never imports keys unprompted" "BUG: imported keys without opt-in" "$out"
check        "key error fails the system step"          "@@STEP_END@@|system|fail" "$out"
check        "key error offers the one-click remedy"    "@@REMEDY@@|import-keys" "$out"
check_re     "the hint carries a 'run:' command the GUI can copy" '@@HINT@@\|.*run: ' "$out"
check        "the run continues to later steps after the key failure" "@@STEP_END@@|cache|ok" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --import-keys imports the signing key and the upgrade then succeeds"
d=$(mktemp -d); setup_common "$d"
export MOCK_KEYDIR="$d"
# `--gpg-auto-import-keys refresh` drops a flag file; the following dup then
# succeeds — modelling a rotated/expired key that the import fixes.
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
keyflag="$MOCK_KEYDIR/keys-imported"
case "$*" in
  *gpg-auto-import-keys*refresh*) : > "$keyflag"; exit 0 ;;
  *refresh*)         exit 0 ;;
  *dup*|*update*)
      if [[ -e "$keyflag" ]]; then echo "3 packages to upgrade."; exit 0
      else echo "Signature verification failed for repository 'oss' (key expired)"; exit 1; fi ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system --import-keys)
check        "--import-keys recovers to a successful step" "@@STEP_END@@|system|ok" "$out"
check_absent "successful import emits no remedy marker"    "@@REMEDY@@" "$out"
unset MOCK_KEYDIR
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --import-keys that still fails does not re-offer the remedy"
d=$(mktemp -d); setup_common "$d"
# Signature failure that importing does NOT clear (key still rejected).
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "Signature verification failed for repository 'oss' (key expired)"; exit 1 ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system --import-keys)
check        "persistent key error still fails the system step" "@@STEP_END@@|system|fail" "$out"
check_absent "no remedy re-offered once keys were already imported" "@@REMEDY@@" "$out"
check_re     "the terminal hint still carries a copyable 'run:' command" '@@HINT@@\|.*run: ' "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo
echo "TEST: a full run fires an end-of-run desktop notification with the outcome"
_notify_case() {  # zypper-dup-output, expected-title, extra-step-mock(optional)
    local dup_out="$1" want="$2"
    local d; d=$(mktemp -d); setup_common "$d"
    cat > "$d/zypper" <<EOF
#!/usr/bin/env bash
[[ "\$1" == "--version" ]] && { echo v; exit 0; }
case "\$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "$dup_out"; exit ${3:-0} ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$d/zypper"
    cat > "$d/notify-send" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$d/notify.log"
EOF
    chmod +x "$d/notify-send"
    run_engine "$d" --steps=system,cache --notify >/dev/null 2>&1
    check "full run notifies: $want" "$want" "$(cat "$d/notify.log" 2>/dev/null)"
    rm -rf "$d"
}
_notify_case "3 packages to upgrade." "Update complete"
_notify_case "Nothing to do."         "Already up to date"
_notify_case "boom"                   "Update failed" 1

# ---------------------------------------------------------------------------
echo "TEST: --skip-repo disables the named source, upgrades the rest, re-enables on exit"
d=$(mktemp -d); setup_common "$d"
# cleanup()'s restore deliberately re-enables via `sudo -n` (never blocks on a
# popup inside the trap). setup_common's shared sudo mock always fails `-n` to
# model "no passwordless drop-in yet" for the auth-status tests; here we model a
# credential the earlier interactive `sudo -A … -v` already warmed, so `-n`
# succeeds too — the real-world behaviour `-n` relies on.
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do case "$1" in -A|-v|-k|-E|-n) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
chmod +x "$d/sudo"
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
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: an interrupted --skip-repo run still re-enables the source (trap restore)"
d=$(mktemp -d); setup_common "$d"
# See the credential-cached sudo mock note in the previous test — same reason.
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do case "$1" in -A|-v|-k|-E|-n) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
chmod +x "$d/sudo"
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
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: an unsafe repo alias is refused and never reaches a privileged command"
d=$(mktemp -d); setup_common "$d"
export MOCK_ZLOG="$d/zypper.log"; : > "$MOCK_ZLOG"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
echo "zypper $*" >> "$MOCK_ZLOG"
case "$*" in *dup*|*update*) echo "Nothing to do."; exit 0;; *) exit 0;; esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system "--skip-repo=evil; rm -rf /")
check_absent "unsafe alias never reaches modifyrepo" "modifyrepo --disable evil" "$(cat "$MOCK_ZLOG")"
unset MOCK_ZLOG
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --auto-skip-repos sets a broken source aside, upgrades the rest, reports ok + notifies"
d=$(mktemp -d); setup_common "$d"
# cleanup()'s restore re-enables via `sudo -n` (never blocks on a popup inside the
# trap). setup_common's shared sudo mock always fails `-n` to model "no
# passwordless drop-in yet" for the auth-status tests; here we model a credential
# the earlier interactive `sudo -A … -v` already warmed, so `-n` succeeds too —
# the real-world behaviour `-n` relies on (same override as the --skip-repo tests).
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do case "$1" in -A|-v|-k|-E|-n) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
chmod +x "$d/sudo"
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
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --auto-skip-repos classifies a corrupt-metadata refresh failure as 'metadata' (M1)"
d=$(mktemp -d); setup_common "$d"
# See the credential-cached sudo mock note on the --skip-repo tests above — same reason.
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do case "$1" in -A|-v|-k|-E|-n) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
chmod +x "$d/sudo"
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
  *"refresh chrome"*)      echo "Valid metadata not found for repository 'chrome'"; exit 1 ;;
  *"refresh oss"*)         exit 0 ;;
  *refresh*)               exit 0 ;;                                   # bulk refresh
  *dup*|*update*)
      if grep -q "modifyrepo --disable chrome" "$MOCK_ZLOG"; then echo "2 packages to upgrade."; exit 0   # retry after skip: OK
      else echo "Valid metadata not found for repository 'chrome'"; exit 1; fi ;;                     # first attempt: blocked
  *needs-rebooting*)       exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system --auto-skip-repos --notify)
check        "metadata failure disables the culprit"       "modifyrepo --disable chrome" "$(cat "$MOCK_ZLOG")"
check        "metadata failure classified as 'metadata'"   "@@REPO_SKIPPED@@|chrome|metadata" "$out"
check        "metadata auto-skip upgrade then succeeds"    "@@STEP_END@@|system|ok" "$out"
check_absent "metadata auto-skip never disables gpg checks" "--no-gpg-checks" "$(cat "$MOCK_ZLOG")"
unset MOCK_ZLOG MOCK_NLOG
rm -rf "$d"

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
rm -rf "$d"

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
rm -rf "$d"

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
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: many Btrfs snapshots warn in pre-flight and offer thinning (ONEUP-0021)"
d=$(mktemp -d); setup_common "$d"
# 30 snapshots (>= the 25 threshold); --print-number still answers the create.
cat > "$d/snapper" <<'EOF'
#!/usr/bin/env bash
[[ "$*" == *--print-number* ]] && { echo 42; exit 0; }
if [[ "$1" == "--no-headers" ]]; then for ((i=0;i<30;i++)); do echo "$i | pre "; done; exit 0; fi
exit 0
EOF
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *dup*|*update*) echo "Nothing to do."; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/snapper" "$d/zypper"
out=$(run_engine "$d" --steps=system)
check "many snapshots warn in pre-flight" "@@SNAPSHOTS@@|warn|30" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: few snapshots do NOT trigger the thin advisory (below threshold)"
d=$(mktemp -d); setup_common "$d"   # default snapper mock lists a single snapshot
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *dup*|*update*) echo "Nothing to do."; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
out=$(run_engine "$d" --steps=system)
check_absent "few snapshots: no thin advisory" "@@SNAPSHOTS@@|warn" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --thin-snapshots runs snapper's cleanup and reports the count removed"
d=$(mktemp -d); setup_common "$d"
export MOCK_SNAPCOUNT="$d/snapcount"; rm -f "$MOCK_SNAPCOUNT"
export MOCK_CLEANLOG="$d/cleanlog"; rm -f "$MOCK_CLEANLOG"
# `cleanup` is recorded; `list` reports 30 before the cleanup, 20 after (call counter,
# same trick as the cache du mock), so the engine sees exactly 10 removed.
cat > "$d/snapper" <<'EOF'
#!/usr/bin/env bash
case "$*" in *cleanup*) echo "$*" >> "$MOCK_CLEANLOG"; exit 0 ;; esac
if [[ "$1" == "--no-headers" ]]; then
    n=$(cat "$MOCK_SNAPCOUNT" 2>/dev/null || echo 0)
    echo $((n + 1)) > "$MOCK_SNAPCOUNT"
    lines=30; [[ "$n" -ge 1 ]] && lines=20
    for ((i=0;i<lines;i++)); do echo "$i | pre "; done
    exit 0
fi
exit 0
EOF
chmod +x "$d/snapper"
out=$(run_engine "$d" --thin-snapshots)
check "thin invokes snapper's number cleanup"   "cleanup number"        "$(cat "$MOCK_CLEANLOG")"
check "thin invokes snapper's timeline cleanup" "cleanup timeline"      "$(cat "$MOCK_CLEANLOG")"
check "thin reports how many were removed"       "@@SNAPSHOTS@@|thinned|10" "$out"
unset MOCK_SNAPCOUNT MOCK_CLEANLOG
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: --thin-snapshots with nothing to remove reports zero (no false claim)"
d=$(mktemp -d); setup_common "$d"   # default snapper: list is a fixed single line
out=$(run_engine "$d" --thin-snapshots)
check "thin with a stable count reports zero removed" "@@SNAPSHOTS@@|thinned|0" "$out"
rm -rf "$d"

# ---------------------------------------------------------------------------
echo "TEST: engine enumerates recent snapshots for the rollback picker (ONEUP-0020)"
d=$(mktemp -d); setup_common "$d"
# `create --print-number` -> 100 (the pre-update point). The machine-readable CSV
# `list --columns` call returns a header row + snapshots incl. #0 (the live
# "current" pseudo-entry, which has no date and must be skipped).
cat > "$d/snapper" <<'EOF'
#!/usr/bin/env bash
[[ "$*" == *--print-number* ]] && { echo 100; exit 0; }
if [[ "$*" == *--columns* ]]; then
    echo "number,date,description"
    echo "0,,current"
    echo "98,2026-07-20 09:00:00,OneUp pre-update 2026-07-20 09:00"
    echo "99,2026-07-22 09:00:00,zypp(zypper)"
    echo "100,2026-07-24 09:00:00,OneUp pre-update 2026-07-24 09:00"
    exit 0
fi
[[ "$1" == "--no-headers" ]] && { echo "100 | single"; exit 0; }
exit 0
EOF
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *dup*|*update*) echo "Nothing to do."; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/snapper" "$d/zypper"
out=$(run_engine "$d" --steps=system)
check "picker lists the pre-update snapshot" \
    "@@SNAPSHOT_ITEM@@|100|2026-07-24 09:00:00|OneUp pre-update 2026-07-24 09:00" "$out"
check "picker lists an older snapshot" \
    "@@SNAPSHOT_ITEM@@|98|2026-07-20 09:00:00|OneUp pre-update 2026-07-20 09:00" "$out"
check_absent "picker skips snapshot 0 (the live 'current' entry)" "@@SNAPSHOT_ITEM@@|0|" "$out"
rm -rf "$d"

echo
echo "======================================"
echo "  Passed: $PASS   Failed: $FAIL"
echo "======================================"
[[ "$FAIL" -eq 0 ]]
