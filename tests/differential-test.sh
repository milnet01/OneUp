#!/usr/bin/env bash
#
# The differential harness — gate G2 of ONEUP-0054.
#
# For each scenario, both engines are run against an IDENTICAL mock sandbox and
# their WHOLE output is compared, along with their exit status. Green means the
# Python engine behaves as update_system.sh does. This is what makes the rewrite
# auditable rather than trusted, and it is why the marker protocol is frozen.
#
# Whole output, not the @@MARKER@@ lines alone. Spec §4.5 describes a marker-only
# diff; the plan's stage 6 records why this is wider. A marker-only diff cannot
# see the banner's position, cannot see console text at all, and cannot see a
# mode that emits no marker — `--emit-guard`, whose body differing by a byte
# stands every passwordless user's toggle down (security.md §5.7), and `--help`.
#
# Two normalisations, and adding a third is how this gate goes blind. §4.5 names
# four — TIMING seconds, log paths, pids and snapshot ids. TIMING's seconds vary
# per run and the mock directory differs per side (which is also §4.5's log-path
# case: run_engine writes the log inside it). The other two CANNOT vary here: no
# marker carries a pid, and the snapshot id and free-space figure come from the
# suite's own snapper and df mocks. Normalising a field that cannot vary does not
# stabilise a gate, it blinds it. Anything genuinely varying between the sides
# makes this harness fail and names itself.
#
# What it cannot see is written down in docs/plans/ONEUP-0054-python-engine.md,
# under "What G2 cannot see" — the list gate G6 checks by hand at stage 8.
#
# No .github/workflows/release.yml entry, against workflow.md §6.1 step 3. That
# rule exists so a gate does not first fail after a tag is pushed; here the
# workflow runs on a `v*` tag, the next one is 2.0.0, and ONEUP-0072 lands before
# it and changes the marker payloads that v1 does not follow — so the entry's
# first CI run would be one the spec already expects not to match. Recorded as
# ONEUP-0195. ONEUP-0072 owns retiring this harness.
#
# Usage:  tests/differential-test.sh        # all scenarios, non-zero on divergence
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1
# shellcheck source=tests/mock-env.sh
source "$HERE/mock-env.sh"

# The two sides, pinned HERE and never inherited. run_engine expands ONE
# ENGINE_CMD, built from the ambient environment when mock-env.sh is sourced —
# so a harness that let ONEUP_ENGINE_CMD through would run v2 against v2 and
# report no divergence having compared nothing. run-tests.sh says the same in its
# own words: "Every reader must agree on that encoding, or gate G2 diffs v1
# against v1 and goes green."
V1_CMD=(bash "$ENGINE")
V2_CMD=(python3 -m oneup.engine)

PASS=0 FAIL=0 SEEN=""

# --- the accepted-divergence list -------------------------------------------
# §4.5: a divergence is either a v2 bug or "a deliberate improvement that gets
# written down here and given its own test", and "Divergence is never waved
# through." So an entry is not a normalisation — it excuses a difference the diff
# has already reported, by name — and it carries a test pinning BOTH sides' text.
# Without that test the entry is a suppression: once the line is excused, every
# later change to it is excused too, and this harness is that line's only reader.
# All four entries are one divergence — `--help` names the program, and the
# program's name genuinely changed: the engine is a package invoked as
# `python3 -m oneup.engine`, not a script called by its filename. They are listed
# line by line rather than matched by a pattern because a pattern would excuse
# any future edit to these lines, which is the suppression this list must not be.
ACCEPT_V1=(
  "Usage: update_system.sh [--steps=LIST] [--check] [--notify] [--log=FILE] [--help]"
  "  update_system.sh                       # update everything"
  "  update_system.sh --steps=system,cache  # only system packages + cache clean"
  "  update_system.sh --check --notify      # background \"updates available?\" check"
)
ACCEPT_V2=(
  "Usage: oneup-engine [--steps=LIST] [--check] [--notify] [--log=FILE] [--help]"
  "  oneup-engine                       # update everything"
  "  oneup-engine --steps=system,cache  # only system packages + cache clean"
  "  oneup-engine --check --notify      # background \"updates available?\" check"
)
ACCEPT_WHY="the program's name genuinely changed: the engine is a package, not a script"

ok()   { printf '  \033[32mok\033[0m   %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }

normalise() {  # $1 = the mock dir to tokenise; stream on stdin
    # Two things vary: the elapsed seconds, and the mock directory (which is also
    # §4.5's log-path case — run_engine writes the log inside it).
    #
    # The seconds appear TWICE, in the same quantity's two renderings: the
    # @@TIMING@@ marker, and the summary line's `%3ds` column. Only the first was
    # normalised at first, and the harness failed on the second within the hour —
    # which is the design working. Both are the same rule; a THIRD kind of field
    # needs the same evidence, never a suspicion.
    sed -E -e "s#$1#<MOCK>#g" \
           -e 's#^(@@TIMING@@\|[a-z]+\|)[0-9]+$#\1<SECS>#' \
           -e 's#^(  \[[A-Z ]{4}\] .{26}) *[0-9]+s#\1 <SECS>s#'
}

# --- mock-set builders ------------------------------------------------------
b_ok() {
    setup_common "$1"
    cat > "$1/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *list-updates*)      echo "S | Repository | Name  | Current | Available | Arch"
                       echo "--+------------+-------+---------+-----------+-----"
                       echo "v | repo       | alpha | 1.0     | 2.0       | x86_64"
                       echo "v | repo       | beta  | 3.1     | 3.2       | x86_64"
                       exit 0 ;;
  *refresh*)           exit 0 ;;
  *--dry-run*)         echo "The following 3 packages are going to be upgraded:"
                       echo "  alpha beta gamma"
                       echo "Overall download size: 12.3 MiB. Already cached: 0 B."
                       exit 0 ;;
  *dup*|*update*)      echo "The following 3 packages are going to be upgraded:"
                       echo "  alpha beta gamma"
                       echo "3 packages to upgrade."
                       exit 0 ;;
  *needs-rebooting*)   exit 0 ;;
  *" lr "*|*"lr -u"*)  echo "1 | repo | X | Yes | (r ) | Yes | http://x" ; exit 0 ;;
  *ps*)                exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$1/zypper"
}

b_dupfail() {
    b_ok "$1"
    cat > "$1/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)          exit 0 ;;
  *--dry-run*)        echo "Nothing to do." ; exit 0 ;;
  *dup*|*update*)     echo "Some of the repositories have not been refreshed" >&2 ; exit 4 ;;
  *needs-rebooting*)  exit 0 ;;
  *" lr "*|*"lr -u"*) echo "1 | repo | X | Yes | (r ) | Yes | http://x" ; exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$1/zypper"
}

b_badrepo() {
    b_ok "$1"
    cat > "$1/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *refresh*)          echo "Repository 'packman' is invalid." >&2 ; exit 6 ;;
  *needs-rebooting*)  exit 0 ;;
  *" lr "*|*"lr -u"*) echo "1 | packman | X | Yes | (r ) | Yes | http://x" ; exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$1/zypper"
}

b_cache() {
    b_ok "$1"
    cat > "$1/du" <<'EOF'
#!/usr/bin/env bash
n=$(cat "$MOCK_DUCOUNT" 2>/dev/null || echo 0)
echo $((n + 1)) > "$MOCK_DUCOUNT"
[[ "$n" -eq 0 ]] && printf '%s\t/var/cache/zypp\n' 2147483648 \
                 || printf '%s\t/var/cache/zypp\n' 1073741824
EOF
    chmod +x "$1/du"
}

b_disklow() {
    b_ok "$1"
    cat > "$1/df" <<'EOF'
#!/usr/bin/env bash
echo "Filesystem     1B-blocks        Used   Available Capacity Mounted on"
echo "/dev/mock  1099511627776 10995116277   104857600       9% ${*: -1}"
EOF
    chmod +x "$1/df"
}

b_checkunknown() {   # a source zypper cannot read -> @@CHECK_UNKNOWN@@
    b_ok "$1"
    cat > "$1/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *list-updates*) echo "Repository 'packman' is invalid." >&2 ; exit 6 ;;
  *refresh*)      exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$1/zypper"
}

b_progress() {       # zypper's own download lines -> @@PROGRESS@@
    b_ok "$1"
    cat > "$1/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *list-updates*)     exit 0 ;;
  *refresh*)          exit 0 ;;
  *--dry-run*)        echo "The following 2 packages are going to be upgraded:"
                      echo "  alpha beta"
                      echo "Overall download size: 2.0 MiB. Already cached: 0 B."
                      exit 0 ;;
  *dup*|*update*)     echo "Overall download size: 2.0 MiB. Already cached: 0 B."
                      echo "Retrieving: alpha-2.0.rpm (1/2),   1.0 MiB"
                      echo "Retrieving: beta-3.2.rpm (2/2),    1.0 MiB"
                      echo "2 packages to upgrade."
                      exit 0 ;;
  *needs-rebooting*)  exit 0 ;;
  *" lr "*|*"lr -u"*) echo "1 | repo | X | Yes | (r ) | Yes | http://x" ; exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$1/zypper"
}

b_services() {       # `zypper ps -sss` naming services -> @@SERVICES@@
    b_ok "$1"
    cat > "$1/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *list-updates*)     exit 0 ;;
  *refresh*)          exit 0 ;;
  *ps*)               echo "sshd" ; echo "cups" ; exit 0 ;;
  *--dry-run*)        echo "Nothing to do." ; exit 0 ;;
  *dup*|*update*)     echo "1 package to upgrade." ; exit 0 ;;
  *needs-rebooting*)  exit 0 ;;
  *" lr "*|*"lr -u"*) echo "1 | repo | X | Yes | (r ) | Yes | http://x" ; exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$1/zypper"
}

b_duperepo() {       # two aliases, one URI in `zypper lr -u` -> @@REPO@@|warn|duplicate
    b_ok "$1"
    cat > "$1/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *list-updates*)     exit 0 ;;
  *" lr "*|*"lr -u"*) echo "1 | oss     | Main | Yes | (r ) | Yes | http://x/oss"
                      echo "2 | oss-alt | Main | Yes | (r ) | Yes | http://x/oss"
                      exit 0 ;;
  *refresh*)          exit 0 ;;
  *--dry-run*)        echo "Nothing to do." ; exit 0 ;;
  *dup*|*update*)     echo "1 package to upgrade." ; exit 0 ;;
  *needs-rebooting*)  exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$1/zypper"
}

b_snapshots() {      # a pile of restore points -> @@SNAPSHOTS@@ and @@SNAPSHOT_ITEM@@
    b_ok "$1"
    cat > "$1/snapper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *--print-number*)   echo 42 ; exit 0 ;;
  *machine-readable*) echo "number,date,description"
                      for i in $(seq 1 30); do
                          printf '%s,2026-01-%02d 10:00:00,"OneUp pre-update %s"\n' "$i" "$((i % 28 + 1))" "$i"
                      done
                      exit 0 ;;
esac
[[ "$1" == "--no-headers" ]] && { for i in $(seq 1 30); do echo "$i | single"; done; exit 0; }
exit 0
EOF
    chmod +x "$1/snapper"
}

b_remedy() {         # a repo-scoped upgrade failure -> @@REMEDY@@|skip-repo
    b_ok "$1"
    cat > "$1/zypper" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *list-updates*)      exit 0 ;;
  *refresh*packman*)   echo "Valid metadata not found for 'packman'." >&2 ; exit 6 ;;
  *refresh*)           exit 0 ;;
  *--dry-run*)         echo "The following 1 package is going to be upgraded:"
                       echo "  alpha"
                       exit 0 ;;
  *dup*|*update*)      echo "Valid metadata not found for repository 'packman'." ; exit 4 ;;
  *needs-rebooting*)   exit 0 ;;
  *" lr "*|*"lr -u"*)  echo "1 | packman | X | Yes | (r ) | Yes | http://x" ; exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$1/zypper"
}

# --- the runner -------------------------------------------------------------
run_pair() {  # name, builder, engine argv...
    local name="$1" builder="$2"; shift 2
    local a b o1 o2 r1 r2 n1 n2 d rest
    a=$(mktemp -d); b=$(mktemp -d)
    "$builder" "$a"; "$builder" "$b"

    ENGINE_CMD=("${V1_CMD[@]}"); export MOCK_DUCOUNT="$a/ducount"
    o1=$(run_engine "$a" "$@"); r1=$?
    ENGINE_CMD=("${V2_CMD[@]}"); export MOCK_DUCOUNT="$b/ducount"
    o2=$(run_engine "$b" "$@"); r2=$?

    SEEN="$SEEN $(grep -oE '@@[A-Z_]+@@' <<<"$o1" | sort -u | tr '\n' ' ')"

    n1=$(normalise "$a" <<<"$o1"); n2=$(normalise "$b" <<<"$o2")
    d=$(diff <(printf '%s\n' "$n1") <(printf '%s\n' "$n2"))

    if [[ "$r1" != "$r2" ]]; then
        bad "$name — exit status differs (v1=$r1 v2=$r2)"
    fi

    if [[ -z "$d" ]]; then
        [[ "$r1" == "$r2" ]] && ok "$name"
        rm -rf "$a" "$b"; return
    fi

    # An accepted entry excuses a reported difference by name; it never removes
    # the line before the comparison. Anything left after that is a divergence.
    rest=$(grep -E '^[<>]' <<<"$d")
    local i
    for i in "${!ACCEPT_V1[@]}"; do
        rest=$(grep -vxF -- "< ${ACCEPT_V1[$i]}" <<<"$rest" | grep -vxF -- "> ${ACCEPT_V2[$i]}")
    done
    rest=$(grep -E '^[<>]' <<<"$rest")

    if [[ -z "$rest" ]]; then
        [[ "$r1" == "$r2" ]] && ok "$name (accepted: $ACCEPT_WHY)"
    else
        bad "$name — unaccepted divergence:"
        head -30 <<<"${rest//$'\n'/$'\n'         }"
    fi
    rm -rf "$a" "$b"
}

# --- each accepted entry's own test -----------------------------------------
# Runs whether or not any scenario diverged, so a change to an accepted line
# fails here even when the diff happens to come back clean.
test_accepted() {
    local d h1 h2 i
    d=$(mktemp -d); b_ok "$d"
    ENGINE_CMD=("${V1_CMD[@]}"); h1=$(run_engine "$d" --help)
    ENGINE_CMD=("${V2_CMD[@]}"); h2=$(run_engine "$d" --help)
    for i in "${!ACCEPT_V1[@]}"; do
        if grep -qxF -- "${ACCEPT_V1[$i]}" <<<"$h1"; then
            ok "accepted[$i] v1 text is as recorded"
        else
            bad "accepted[$i] v1 text has changed — expected: ${ACCEPT_V1[$i]}"
        fi
        if grep -qxF -- "${ACCEPT_V2[$i]}" <<<"$h2"; then
            ok "accepted[$i] v2 text is as recorded"
        else
            bad "accepted[$i] v2 text has changed — expected: ${ACCEPT_V2[$i]}"
        fi
    done
    rm -rf "$d"
}

# --- marker coverage --------------------------------------------------------
# Reported by the harness rather than claimed in a document, so it cannot go
# stale. NOTE that marker coverage is not scenario coverage: a mode emitting no
# marker can never appear here however thoroughly it is missed, which is why
# --emit-guard and --help are scenarios in their own right.
# Empty today: every marker in the reference table is produced by a scenario. An
# entry here is a marker no mock sandbox can reach, and it needs its reason beside
# it — G6 then checks it by hand (the plan's "What G2 cannot see").
UNREACHABLE=""
UNREACHABLE_WHY="see the plan's 'What G2 cannot see'"

coverage() {
    local table seen missing m
    # shellcheck disable=SC2016  # the backticks are markdown in the table, not a subshell
    table=$(grep -oE '^\| `@@[A-Z_]+@@`' docs/reference/marker-protocol.md \
            | grep -oE '@@[A-Z_]+@@' | sort -u)
    seen=$(tr ' ' '\n' <<<"$SEEN" | grep -E '@@[A-Z_]+@@' | sort -u)
    missing=""
    for m in $table; do
        grep -qxF "$m" <<<"$seen" || missing="$missing $m"
    done
    printf '\nMarker coverage: %s of %s produced by a scenario\n' \
        "$(grep -c . <<<"$seen")" "$(grep -c . <<<"$table")"
    if [[ -z "${missing// /}" ]]; then
        ok "every marker in the reference table is produced by a scenario"
        return
    fi
    local unexplained=""
    for m in $missing; do
        grep -qw -- "$m" <<<"$UNREACHABLE" || unexplained="$unexplained $m"
    done
    printf '  not produced: %s\n' "${missing# }"
    if [[ -z "${unexplained// /}" ]]; then
        ok "every unproduced marker is on the unreachable list ($UNREACHABLE_WHY)"
    else
        bad "unproduced and not explained:${unexplained}"
    fi
}

# --- scenarios --------------------------------------------------------------
echo "Differential: update_system.sh vs python3 -m oneup.engine"
run_pair "--check"                b_ok      --check
run_pair "--check --notify"       b_ok      --check --notify
run_pair "--size=system"          b_ok      --size=system
run_pair "--auth-status"          b_ok      --auth-status
run_pair "--emit-guard"           b_ok      --emit-guard
run_pair "--help"                 b_ok      --help
run_pair "full run"               b_ok
run_pair "system step only"       b_ok      --steps=system
run_pair "flatpak step only"      b_ok      --steps=flatpak
run_pair "cache step (@@FREED@@)" b_cache   --steps=cache
run_pair "low disk (@@DISK@@)"    b_disklow --steps=system
run_pair "dup fails"              b_dupfail --steps=system
run_pair "refresh finds a bad repo" b_badrepo --steps=system
run_pair "--check with items"     b_ok      --check
run_pair "--check, source unreadable" b_checkunknown --check
run_pair "download progress"      b_progress --steps=system
run_pair "services need restart"  b_services --steps=system
run_pair "duplicate repository"   b_duperepo --steps=system
run_pair "--skip-repo"            b_ok      --steps=system --skip-repo=packman
run_pair "many restore points"    b_snapshots --steps=system
run_pair "repo-scoped failure"    b_remedy  --steps=system
test_accepted
coverage

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]] || exit 1
