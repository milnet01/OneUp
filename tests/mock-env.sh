#!/usr/bin/env bash
#
# The mock sandbox, shared by every suite that drives an engine.
#
# ONEUP-0054 stage 6: tests/differential-test.sh runs both engines against the
# same mocks and diffs their output, so its whole claim is that the two sides saw
# an IDENTICAL sandbox. A second copy of setup_common would drift from this one
# silently, with both suites staying green the entire time — so there is one
# copy, and both suites source it.
#
# Sourced, never executed: it defines ENGINE, ENGINE_CMD, setup_common,
# setup_cached_sudo and run_engine, and runs nothing.
#
# The repository root is resolved from ${BASH_SOURCE[0]} rather than $0, which in
# a sourced file names the SOURCING script. Measured while this file was being
# split out: with $0, sourcing the block from a script outside tests/ pointed
# ENGINE at a path that does not exist, and the run failed with exit 127 instead
# of producing a diff — a differential harness that reports "engine missing" and
# a differential harness that reports "no divergence" both exit non-zero and
# zero for the wrong reasons.

ENGINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/update_system.sh"

# ONEUP-0054 §4.4: which engine the suite drives. The override is a SCALAR
# environment variable word-split into argv HERE, because a Bash array cannot
# cross a process boundary — `export` drops it, so a caller that sets one hands
# the suite nothing. Two words by default; `python3 -m oneup.engine` is three.
# Every reader must agree on that encoding, or gate G2 diffs v1 against v1 and
# goes green. `read -r -a` rather than an unquoted expansion: the latter globs
# as well as splits, so a value containing `*` would expand against the cwd.
# The default is built as a quoted array literal, so the absolute $ENGINE path
# survives a space in it.
if [[ -n "${ONEUP_ENGINE_CMD:-}" ]]; then
    read -r -a ENGINE_CMD <<<"$ONEUP_ENGINE_CMD"
else
    ENGINE_CMD=(bash "$ENGINE")
fi

# --- mock system tools common to every scenario ----------------------------
#
# NOTE: there is deliberately no `zypper` here, because almost every scenario
# needs a DIFFERENT one and a shared default would be overwritten by all of
# them. The consequence is easy to miss: a scenario that exercises the system
# step and forgets its own zypper mock reaches the REAL zypper on the
# developer's box, under a sudo mock that just execs -- so it fails as the
# test user rather than doing damage, but its result now depends on the
# machine, which docs/standards/testing.md §2 forbids. Measured 2026-09-03,
# while writing the ONEUP-0054 INV-11 scenario: the run came back "1 error"
# and looked like an engine bug. If your scenario runs `--steps=system`,
# write a zypper mock.
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
    # The engine's pre-flight reads `df -PB1 <mount>` for / and /var. Unmocked it reads
    # the real machine, so on a box under the 2 GiB threshold every system-step scenario
    # gains a real @@DISK@@|warn line sourced from whatever the developer's disk happens
    # to be doing that afternoon. Report ample space; a scenario that wants the warning
    # overwrites this mock the same way scenarios overwrite zypper.
    cat > "$d/df" <<'EOF'
#!/usr/bin/env bash
# Mimics `df -PB1 <mount>`: header line, then the POSIX row whose 4th field is bytes free.
echo "Filesystem     1B-blocks        Used   Available Capacity Mounted on"
echo "/dev/mock  1099511627776 10995116277 500000000000       3% ${*: -1}"
EOF
    chmod +x "$d"/*
    # ONEUP-0094: the download-recovery trigger reads the repository definitions, and
    # run_engine points ONEUP_REPOS_DIR here. Seeded rather than left empty on purpose —
    # recovery declines when no download.opensuse.org baseurl is present, so an empty
    # directory would make every recovery scenario silently exercise the SKIP path while
    # looking like it tested recovery. The alias deliberately contains the host name: an
    # unanchored rewrite renames it, which is the cache-losing bug INV-3 exists to catch.
    mkdir -p "$d/repos.d"
    cat > "$d/repos.d/oss.repo" <<'EOF'
[download.opensuse.org-oss]
name=Main Repository (OSS)
enabled=1
baseurl=http://download.opensuse.org/tumbleweed/repo/oss/
EOF
    cat > "$d/repos.d/packman.repo" <<'EOF'
[packman]
name=Packman
enabled=1
baseurl=https://ftp.gwdg.de/pub/linux/misc/packman/suse/openSUSE_Tumbleweed/
EOF
}

# Overwrite setup_common's sudo with one whose credential is already warm.
#
# setup_common's shared mock always fails `sudo -n` to model a box WITHOUT the
# ONEUP-0023 passwordless drop-in, so sudo_init falls through to the interactive
# validate + keep-alive path. Some scenarios need the opposite: cleanup()'s restore
# deliberately re-enables via `sudo -n` (it must never block on a popup inside the
# trap), which only works when an earlier interactive `sudo -A … -v` has warmed the
# credential. This mock is that box — `-n` succeeds too.
setup_cached_sudo() {
    local d="$1"
    cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do case "$1" in -A|-v|-k|-E|-n) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
    chmod +x "$d/sudo"
}

# Run the engine with a given mock dir; echo its combined output.
run_engine() {
    local mockdir="$1"; shift
    # Redirect every path that reaches outside the mock dir, unless the scenario set it
    # itself. Two ways this bit for real:
    #   * the package-lock probe defaults to /run/zypp.pid, so every scenario failed
    #     whenever the machine happened to be running zypper — precisely when someone is
    #     working on an update tool;
    #   * run.state defaults to the user's own, and cleanup() deletes the file it owns —
    #     so running the suite during a real update deleted that run's record, and the
    #     window could no longer find the run it was following (ONEUP-0045).
    # A test must never depend on, or damage, the state of the box it runs on.
    #   * the shutdown inhibitor re-execs the engine under the REAL systemd-inhibit,
    #     so every scenario would take a genuine block-mode lock on the tester's own
    #     session (ONEUP-0086). Pre-set here, and note the `-` rather than `:-`: a
    #     scenario opts back IN by setting it to the empty string.
    PATH="$mockdir:$PATH" \
        ONEUP_ZYPP_PID_FILE="${ONEUP_ZYPP_PID_FILE:-$mockdir/no-zypp.pid}" \
        ONEUP_RUN_STATE="${ONEUP_RUN_STATE:-$mockdir/run.state}" \
        ONEUP_STOP_FILE="${ONEUP_STOP_FILE:-$mockdir/stop.request}" \
        ONEUP_HOLD_STATE="${ONEUP_HOLD_STATE:-$mockdir/hold.state}" \
        ONEUP_GO_FILE="${ONEUP_GO_FILE:-$mockdir/go.request}" \
        ONEUP_GUARD_FILE="${ONEUP_GUARD_FILE:-$mockdir/oneup-download-guard}" \
        ONEUP_INHIBITED="${ONEUP_INHIBITED-1}" \
        ONEUP_REPOS_DIR="${ONEUP_REPOS_DIR:-$mockdir/repos.d}" \
        "${ENGINE_CMD[@]}" "$@" --log="$mockdir/run.log" 2>&1
}
