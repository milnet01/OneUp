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
# Strip sudo's own options; a bare `sudo -v` (validate) just succeeds.
while [[ $# -gt 0 ]]; do
    case "$1" in
        -A|-n|-v|-k|-E) shift ;;
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
# Diff the set of `sleep 50` processes (the keep-alive's idle) across the run:
# anything new that survives is an orphan cleanup failed to reap. -xf matches the
# full command line exactly, so this harness's own long argv can't false-match.
ka_before=$(pgrep -xf 'sleep 50' | sort)
run_engine "$d" --steps=system >/dev/null 2>&1
sleep 0.4   # let the process-group kill propagate
ka_after=$(pgrep -xf 'sleep 50' | sort)
ka_leaked=$(comm -13 <(echo "$ka_before") <(echo "$ka_after") | grep -v '^$' || true)
if [[ -z "$ka_leaked" ]]; then
    echo "  ok   - no orphaned keep-alive after the run"; PASS=$((PASS+1))
else
    echo "  FAIL - keep-alive orphaned a process: $ka_leaked"; FAIL=$((FAIL+1))
    echo "$ka_leaked" | xargs -r kill 2>/dev/null
fi
rm -rf "$d"

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
echo
echo "======================================"
echo "  Passed: $PASS   Failed: $FAIL"
echo "======================================"
[[ "$FAIL" -eq 0 ]]
