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
echo
echo "======================================"
echo "  Passed: $PASS   Failed: $FAIL"
echo "======================================"
[[ "$FAIL" -eq 0 ]]
