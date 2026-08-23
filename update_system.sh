#!/usr/bin/env bash
#
# System Updater engine — openSUSE Tumbleweed / Leap
#
# Usable two ways:
#   1. Standalone in a terminal:  ./update_system.sh            (runs everything)
#                                 ./update_system.sh --steps=cache
#   2. Driven by the System Updater GUI (updater.py), which selects steps via
#      --steps and reads the @@MARKER@@ progress lines this script prints.
#
# Design notes:
#   * Each job is a selectable step (system, flatpak, firmware, orphans, cache).
#     With no --steps flag every step runs, preserving the original behaviour.
#   * We authenticate ONCE up front (sudo -v via the KDE askpass popup) and keep
#     the credential warm, so the whole run needs a single password prompt
#     instead of one per command.
#   * A step that fails is recorded and the run CONTINUES to the next step, so
#     the end-of-run summary is always useful and cache cleanup still happens.
#   * Progress markers (lines starting with @@) are for the GUI to parse; in a
#     terminal they are harmless one-liners.

# Strict mode: -u catches unset-variable typos; -o pipefail surfaces a failure on
# the left of a pipe. NOT -e — the design deliberately continues past a failed step
# (via `|| ok=false`) so the end-of-run summary and cache cleanup still happen.
set -uo pipefail

# Overridable so the test suite can point it at a mock instead of raising a real KDE
# dialog. The default is KDE's helper, which is what this app targets.
ASKPASS="${ONEUP_ASKPASS:-/usr/libexec/ssh/ksshaskpass}"
# EXPORTED, not just set: sudo falls back to the askpass helper only when it finds
# SUDO_ASKPASS in the environment. Without the export, a `sudo` that can't see
# sudo_init's cached credential has no way to ask and dies with "a terminal is
# required to read the password" — there is no terminal, because the GUI runs this
# script through QProcess. That is not hypothetical: it is what made "Show download
# size" fail (ONEUP-0036). sudo_init's credential is not always visible to a later
# call — `out=$(sudo …)` runs in a subshell, and with no tty sudo keys its
# credential record on the parent process id, which the subshell changes. Exporting
# this turns that from a hard failure into (at worst) one graphical prompt, and
# makes the project convention — privileged commands raise the KDE prompt, never
# block on stdin — true for every sudo in this file rather than just the -A ones.
export SUDO_ASKPASS="$ASKPASS"
# Label EVERY prompt sudo may raise, including ones we didn't pass -p to. sudo's
# own default reads "[sudo] password for root" under this distro's `targetpw`
# default — an unlabelled request for the ROOT password looks like something
# nefarious to a user who only clicked "check the download size". A prompt the
# user can't attribute is a prompt they should refuse, so it must always say who
# is asking and why (ONEUP-0037).
export SUDO_PROMPT="OneUp needs administrator rights to update this system. Password: "

# ---------------------------------------------------------------------------
# Configuration / arguments
# ---------------------------------------------------------------------------
ALL_STEPS="system,flatpak,firmware,orphans,cache"
STEPS="$ALL_STEPS"
LOG_DIR="$HOME/Documents/update-logs"
LOG_FILE=""
# A real run records itself here so a GUI that starts (or restarts) mid-run can find
# it, say so, and follow the log instead of letting the user launch a second run that
# can only fail on the package lock (ONEUP-0045). Runs now deliberately outlive the
# window (ONEUP-0042), which is exactly what makes this necessary. Overridable for tests.
# XDG state base (ONEUP-0059). XDG_STATE_HOME wins when it is set to an ABSOLUTE
# path; anything else — unset, empty, or relative — falls back to the
# specification's own default. `oneup/gui/paths.py`'s _state_home applies the
# IDENTICAL rule: run.state and stop.request are a contract between the two
# halves, so a disagreement here has the window writing stop.request where this
# engine never looks, and Stop quietly stops working with nothing failing
# anywhere (docs/design/oneup-2.0.md §6.5).
if [[ ${XDG_STATE_HOME:-} == /* ]]; then
    ONEUP_STATE_DIR="$XDG_STATE_HOME/oneup"
else
    ONEUP_STATE_DIR="$HOME/.local/state/oneup"
fi
RUN_STATE_FILE="${ONEUP_RUN_STATE:-$ONEUP_STATE_DIR/run.state}"
# The GUI asks for a stop by creating this file. Deliberately COOPERATIVE rather than a
# signal: the engine honours it only at a safe boundary — between steps, and after the
# repo refresh but before the transaction starts. Signalling the engine mid-transaction
# would leave rpm half-applied, or orphan a zypper that carries on regardless, which is
# the failure this project takes most seriously (ONEUP-0047). Overridable for tests.
STOP_FILE="${ONEUP_STOP_FILE:-$ONEUP_STATE_DIR/stop.request}"
# --hold's two files (ONEUP-0044 §4.3). They sit beside the pair above, in the same
# directory the marker reference's §8 pins, and they are a contract between the two
# halves in the same way — NOT part of the marker protocol, because the window writes
# one of them. hold.state is this engine's stamp: the window reads its line 1 to tell a
# live hold from one a SIGKILLed engine left behind, and the engine compares go.request
# and stop.request against its mtime to reject a leftover from an earlier session.
HOLD_STATE_FILE="${ONEUP_HOLD_STATE:-$ONEUP_STATE_DIR/hold.state}"
GO_FILE="${ONEUP_GO_FILE:-$ONEUP_STATE_DIR/go.request}"
STOP_HONOURED=false
CHECK_ONLY=false   # --check: report what WOULD update, install nothing, no root
NOTIFY=false       # --notify: fire a desktop notification if updates are found
SIZE_STEP=""       # --size=<step>: on-demand exact download size (needs root)
HOLD=false         # --hold: after --size has quoted the size, stay alive waiting for the
                   # window's go-ahead instead of exiting, so the run that follows reuses
                   # the credential THIS process already cached. Ignored without --size.
HOLD_SIZE=""       # the size run_size quoted, for hold.state line 3
HELD_AUTH=false    # true once a hold has been honoured: this process authenticated for
                   # the preview and must NOT re-enter sudo_init on the way into the run.
HOLD_SECONDS="${ONEUP_HOLD_SECONDS:-120}"  # the hold ends by itself after this long. Two
                   # independent reasons it must (ONEUP-0044 §4.4): sudo's cached
                   # credential expires, so a longer hold would reach its go-ahead cold
                   # and prompt again — the very second dialog this fixes; and a held
                   # engine is unattended privilege with nobody left to authorise it.
# Whose departure ends the hold. Under QProcess the engine is a direct child of the
# window, so $PPID at shell start IS the window. Captured ONCE here and afterwards asked
# with `kill -0` — the idiom sudo_init's keep-alive already uses. Do NOT re-read $PPID to
# detect the change: bash sets it once at shell start and never refreshes it on
# reparenting, so the comparison is a constant against a copy of itself and can never
# fire (measured: a child whose parent exited kept $PPID=170203 for its whole life while
# its real parent moved to 1309). Nor test it against 1 — systemd reparents a user
# session's orphans to `systemd --user`, the mistake reap_orphaned_askpass already paid
# for. Both spellings read as a guard and are dead code.
WINDOW_PID=$PPID
AUTH_ACTION=""     # --grant-auth / --revoke-auth / --auth-status: manage the
                   # opt-in "remember my authorization" sudoers drop-in.
IMPORT_KEYS=false  # --import-keys: refresh with --gpg-auto-import-keys so a rotated
                   # or expired repo signing key is imported for the system upgrade.
                   # Opt-in per run (the GUI sets it only after a warned confirmation).
SKIP_REPOS=()      # --skip-repo=<alias> (repeatable): sources to set aside this run
AUTO_SKIP=false    # --auto-skip-repos: unattended auto-quarantine of a broken source
DISABLED_REPOS=()  # aliases WE disabled this run; cleanup() re-enables every one
MAX_SKIP_REPOS=2   # more than this failing at once = systemic, don't silently skip
THIN_SNAPSHOTS=false  # --thin-snapshots: run snapper's own retention cleanup to drop
                      # expendable Btrfs restore points (guarded; never a hand-pick).
SNAP_WARN_COUNT=25    # pre-flight: warn once this many Btrfs snapshots have piled up
                      # (each zypper transaction leaves a pre/post pair, so they add up).
STOP_POLL_SECONDS="${ONEUP_STOP_POLL_SECONDS:-2}"  # how often the download pass looks for a
                      # stop request (ONEUP-0085). "Stop within seconds" means this plus
                      # zypper's own exit; overridable so the suite need not wait one out.
SYS_STOPPED=false     # set when the user stopped during/after the download pass, which is
                      # a SKIP rather than a failure — nothing was installed.
SYS_DL_RC=0           # the download pass's exit status; 143 (128+SIGTERM) means stopped.
declare -a SYS_TXN=() # the transaction argv, built once by system_txn_argv (INV-5).
REPOS_DIR="${ONEUP_REPOS_DIR:-/etc/zypp/repos.d}"  # where repository definitions are read
                      # from. Overridable so the suite never reads — or depends on — the
                      # repository list of the machine it runs on (testing.md §2).
REPOSD_OVERRIDE=""    # non-empty only during download recovery: the temporary copy of
                      # REPOS_DIR whose openSUSE baseurls point at the content CDN
                      # (ONEUP-0094). Cleared on every exit from run_system_upgrade.
CDN_REPOSD_DIR=""     # the same directory, kept for CLEANUP after REPOSD_OVERRIDE is
                      # cleared — two variables because the flag's lifetime (one
                      # transaction) is shorter than the directory's (the whole step).
DL_RECOVERY_TRIED=false  # recovery was ATTEMPTED this run — not that it succeeded.
DL_RETRY_FAILED=false    # recovery ran and its download pass failed. What the hint arm
                      # guards on: DL_RECOVERY_TRIED is still true when the retry worked
                      # and the commit then failed, and announcing "nothing was installed"
                      # there would be a silent wrong answer (workflow.md §1.1).
SYS_LOG_FIRST=""      # snapshot of the first attempt's log. The retry's `tee` truncates
                      # SYS_LOG, so the failing package's name only survives here.
REFRESH_TIMEOUT="${ONEUP_REFRESH_TIMEOUT:-120}"   # per-repository refresh budget, seconds.
                      # zypper has no timeout of its own: a mirror trickling metadata at
                      # 1 KB/s once held a run for hours with nothing on screen. Overridable
                      # so the tests don't have to wait out a real one (ONEUP-0048).

# The refresh and the cache measurement both run under sudo, so the ONEUP-0023 drop-in must
# grant the EXACT argv each types or passwordless silently keeps prompting (ONEUP-0092).
# One definition each, used by the call site AND by auth_cmnds, so the rule cannot drift
# from the call. Absolute paths because sudoers refuses a bare command name outright
# ("expected a fully-qualified path name") — a rule carrying one is rejected whole.
REFRESH_SUDO_ARGV=("$(command -v timeout)" "$REFRESH_TIMEOUT" zypper)
CACHE_DU_ARGV=("$(command -v du)" -sB1 /var/cache/zypp)

# The root-side download wrapper, as a root-owned file rather than an argument to bash
# (ONEUP-0092 §4.3). `env LC_ALL=C bash -c *` cannot be granted — it is a root shell in
# sudoers clothing — but a script that can only exec one pinned zypper grants exactly what
# the drop-in's first entry already does. Installed by --grant-auth, removed by
# --revoke-auth. /usr/libexec per FHS 3.0 (Tumbleweed since 2020), /usr/lib on Leap 15.x.
GUARD_DIR=$([[ -d /usr/libexec ]] && echo /usr/libexec || echo /usr/lib)
GUARD_FILE="${ONEUP_GUARD_FILE:-$GUARD_DIR/oneup-download-guard}"

usage() {
    cat <<EOF
System Updater engine

Usage: $(basename "$0") [--steps=LIST] [--check] [--notify] [--log=FILE] [--help]

  --steps=LIST   Comma-separated steps to run. Default: all.
                 Available: system, flatpak, firmware, orphans, cache
  --check        Read-only: report how many updates are available and exit.
                 Runs WITHOUT root, so it is safe for an unattended timer.
  --notify       Raise a desktop notification: with --check when updates exist,
                 and at the end of a full run with the outcome.
  --grant-auth   Opt in to passwordless updates: install a scoped sudoers rule
                 so OneUp's update commands run without a password (stores no
                 password). Asks for your password once to set it up.
  --revoke-auth  Remove that rule — updates prompt for a password again.
  --auth-status  Print whether the passwordless rule is active (@@AUTH@@|on/off).
  --import-keys  Refresh with --gpg-auto-import-keys so a rotated/expired repo
                 signing key is imported for the system upgrade (opt-in per run).
  --skip-repo=ALIAS  Exclude this source from the run: disable it, upgrade the
                 rest, re-enable it. Repeatable.
  --auto-skip-repos  Unattended mode: on a repo-scoped failure, auto-detect and
                 skip the culprit(s) (up to $MAX_SKIP_REPOS), then continue.
  --thin-snapshots  Ask snapper to remove old, expendable Btrfs snapshots (its own
                 retention cleanup — keeps the recent ones), then report how many.
  --log=FILE     Write the run log here. Default: $LOG_DIR/<timestamp>.log
  --help         Show this help.

Examples:
  $(basename "$0")                       # update everything
  $(basename "$0") --steps=system,cache  # only system packages + cache clean
  $(basename "$0") --check --notify      # background "updates available?" check
EOF
}

for arg in "$@"; do
    case "$arg" in
        --steps=*) STEPS="${arg#*=}" ;;
        --log=*)   LOG_FILE="${arg#*=}" ;;
        --check)   CHECK_ONLY=true ;;
        --size=*)  SIZE_STEP="${arg#*=}" ;;
        --hold)    HOLD=true ;;
        --grant-auth)  AUTH_ACTION="grant" ;;
        --revoke-auth) AUTH_ACTION="revoke" ;;
        --auth-status) AUTH_ACTION="status" ;;
        --emit-guard)  AUTH_ACTION="emit-guard" ;;
        --import-keys) IMPORT_KEYS=true ;;
        --skip-repo=*)     SKIP_REPOS+=("${arg#*=}") ;;
        --auto-skip-repos) AUTO_SKIP=true ;;
        --thin-snapshots)  THIN_SNAPSHOTS=true ;;
        --notify)  NOTIFY=true ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

step_selected() { [[ ",$STEPS," == *",$1,"* ]]; }

# ---------------------------------------------------------------------------
# Shutdown inhibitor: hold one for the whole run (ONEUP-0086).
# ---------------------------------------------------------------------------
# zypper runs as ROOT inside the user's session cgroup, and `systemd --user` is not
# permitted to kill root processes — the journal says so in as many words:
#   Failed to kill control group /user.slice/.../OneUp-tray@autostart.service,
#   ignoring: Operation not permitted
# So a logout or reboot asked for mid-run waits on something it can never stop, long
# after the desktop has been torn down: the user sees a black screen that never
# reboots, and eventually holds the power button — which is the worst possible moment
# to cut power to an rpm transaction. A block-mode inhibitor turns that silent hang
# into a visible prompt naming OneUp, which the user can still override.
#
# Re-exec rather than a background lock-holder, because the lock then lives exactly as
# long as this process and there is nothing left behind if we are SIGKILLed (§2.4:
# nothing the engine spawns may outlive it). Arg parsing above uses `for arg in "$@"`
# and never shifts, so "$@" is still the original command line here.
#
# Probed, not assumed — same reasoning as the tee -p probe below. `systemd-inhibit`
# exits WITHOUT running its command if it cannot take the lock (no logind, a container,
# a locked-down session), which would turn a missing convenience into a failed update.
# A missing or non-working tool must degrade to "no inhibitor", never to "no run".
if [[ -z "${ONEUP_INHIBITED:-}" && -z "$AUTH_ACTION" && -z "$SIZE_STEP" ]] \
   && ! $CHECK_ONLY \
   && systemd-inhibit --what=shutdown --who=OneUp --why=probe true >/dev/null 2>&1; then
    export ONEUP_INHIBITED=1
    exec systemd-inhibit \
        --what=shutdown:sleep --mode=block --who="OneUp" \
        --why="Installing updates — interrupting now can leave packages half-installed" \
        "$0" "$@"
fi

# ---------------------------------------------------------------------------
# Logging: mirror everything to the log file as well as the console/GUI.
# ---------------------------------------------------------------------------
mkdir -p "$LOG_DIR"
if [[ -z "$LOG_FILE" ]]; then
    LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d_%H%M).log"
fi
# -p (--output-error=warn-nopipe) is what lets a run survive the GUI going away
# (ONEUP-0042). Our stdout is a pipe to the GUI; when the user quits, plain `tee` dies
# on the broken pipe, and the engine then takes a SIGPIPE on its next line and is
# killed WITHOUT running its cleanup trap. That is what happened to a real run: the
# keep-alive was left looping, and zypper was orphaned mid-transaction — which is the
# one thing that must never happen, since a half-applied rpm transaction can leave
# packages broken, and the abandoned lock then blocked the next two runs. With -p, tee
# keeps writing the log alone, so the engine never notices and finishes the job
# properly. Probed rather than assumed: a tee without -p degrades to the old
# behaviour (the PIPE trap below then at least runs cleanup) instead of breaking
# every run with a usage error on a pipe nobody reads.
tee_opts=(-a)
echo | tee -p /dev/null >/dev/null 2>&1 && tee_opts+=(-p)
exec > >(tee "${tee_opts[@]}" "$LOG_FILE") 2>&1

# ---------------------------------------------------------------------------
# Progress-marker helpers (consumed by the GUI; benign in a terminal).
#   @@STEP_BEGIN@@|key|index|total|Human label
#   @@STEP_END@@|key|ok|skip|fail|detail
#   @@TIMING@@|key|seconds               (how long the step took)
#   @@PROGRESS@@|key|done|total|phase[|bytes|bytes_total]
#                                        (live per-package progress within a step;
#                                         phase is download|install, and total 0
#                                         means zypper gave no denominator. The two
#                                         byte fields are optional — present only in the
#                                         download phase once zypper has printed a size —
#                                         and a bytes_total of 0 means "not known yet")
#   @@REFRESH@@|done|total|alias         (refreshing this repository, done-of-total)
#   @@SNAPSHOT@@|id
#   @@SNAPSHOT_ITEM@@|id|date|description (rollback picker: one recent restore point)
#   @@CHECK@@|key|count|label            (--check mode: updates available)
#   @@CHECK_ITEM@@|key|name|from|to      (--check mode: one changed package)
#   @@CHECK_UNKNOWN@@|key|reason         (--check mode: this step's answer is NOT
#                                         trustworthy — a source couldn't be read)
#   @@SIZE@@|key|download                (--size mode: total download size)
#   @@FREED@@|key|human                  (disk reclaimed by the cache clean)
#   @@AUTH@@|on|off                      (passwordless-authorization state)
#   @@DISK@@|warn|mount|free             (pre-flight: low disk space)
#   @@SNAPSHOTS@@|warn|count             (pre-flight: many Btrfs snapshots may be using disk)
#   @@SNAPSHOTS@@|thinned|removed        (--thin-snapshots: how many snapshots were cleaned up)
#   @@REPO@@|warn|reason                 (pre-flight: repo health issue)
#   @@HINT@@|plain-English failure hint
#   @@REMEDY@@|import-keys               (a one-click GUI fix is available for this failure)
#   @@REPO_SKIPPED@@|alias|reason        (a source was set aside this run)
#   @@REMEDY@@|skip-repo|alias           (offer "Skip <source> & update the rest")
#   @@SERVICES@@|svc1 svc2 …             (services to restart instead of rebooting)
#   @@INSTALLED@@|count|sys_changed|fw_changed   (yes/no flags for the summary)
#   @@REBOOT@@|yes|no[|reason]           (reason names why, e.g. "a new kernel … was installed")
#   @@DONE@@|ok|errors
# ---------------------------------------------------------------------------
marker() { printf '@@%s@@|%s\n' "$1" "$2"; }

# Build a plain-English phrase naming the components that make a reboot matter —
# a new kernel, graphics drivers, or out-of-tree (DKMS/KMP) driver modules — by
# scanning this run's system transaction log ($1). Echoes e.g. "a new kernel and
# your NVIDIA graphics driver were installed", or nothing if no such component
# was in the transaction. Purely cosmetic: it NAMES a reboot the engine already
# decided to advise and never changes that decision, so it can only report what
# was actually installed this run — it can never invent one.
reboot_reason_from_log() {  # transaction-log path
    local log="${1:-}"; [[ -f "$log" ]] || return 0
    local -a parts=()
    grep -qE '\bkernel-(default|preempt|rt|64kb|lpae|kvmsmall|vanilla)\b' "$log" \
        && parts+=("a new kernel")
    if grep -qiE '\bnvidia' "$log"; then
        parts+=("your NVIDIA graphics driver")
    elif grep -qE '\b(Mesa|xf86-video-|libvulkan|libdrm)' "$log"; then
        parts+=("your graphics driver")
    fi
    # DKMS / kernel-module packages other than the NVIDIA one already named above.
    if grep -E '(-kmp-|\bdkms\b)' "$log" 2>/dev/null | grep -qvi nvidia; then
        parts+=("kernel driver modules")
    fi
    (( ${#parts[@]} )) || return 0
    local phrase verb="were"; (( ${#parts[@]} == 1 )) && verb="was"
    case ${#parts[@]} in           # at most three categories, so an explicit join is clearest
        1) phrase="${parts[0]}" ;;
        2) phrase="${parts[0]} and ${parts[1]}" ;;
        *) phrase="${parts[0]}, ${parts[1]}, and ${parts[2]}" ;;
    esac
    echo "$phrase $verb installed"
}

# Fire a desktop notification (best-effort; silently skipped if unavailable).
notify_send() {  # title, body
    command -v notify-send &>/dev/null \
        && notify-send -a "OneUp" -i za.co.antsprojectshub.OneUp "$1" "$2" 2>/dev/null || true
}

# Ordered list of the steps we will actually run, and a human label for each.
# The =() is load-bearing: under `set -u` an array declared but never assigned
# (empty --steps → no elements appended) counts as unset, so ${#RUN_KEYS[@]}
# would abort with "unbound variable" before the TOTAL==0 guard could report it.
declare -a RUN_KEYS=()
declare -A LABEL=(
    [system]="Updating system packages"
    [flatpak]="Updating Flatpak apps"
    [firmware]="Checking firmware updates"
    [orphans]="Removing leftover packages"
    [cache]="Cleaning package cache"
)
for k in system flatpak firmware orphans cache; do
    step_selected "$k" && RUN_KEYS+=("$k")
done
TOTAL=${#RUN_KEYS[@]}
STEP_INDEX=0

# Reject an empty or all-unknown step set outright: running nothing and then
# reporting a clean "@@DONE@@|ok" would hide a --steps typo (e.g. --steps=sytem).
if (( TOTAL == 0 )); then
    echo "No valid update steps selected (got --steps=\"$STEPS\")." >&2
    echo "Valid steps: $ALL_STEPS" >&2
    exit 2
fi

# Per-step outcome tracking for the final summary.
declare -A RESULT   # key -> ok|skip|fail
declare -A DETAIL   # key -> short note
declare -A SECS     # key -> elapsed seconds
ERRORS=0
SYS_CHANGED=false   # did the system step actually install/upgrade anything?
SYS_COUNT=""        # best-effort count of system packages changed
SYS_REBOOT_DETAIL=""  # plain-English "why a reboot matters" phrase (kernel/driver names)
FW_CHANGED=false    # did firmware updates get applied?

# True once the user has asked to stop. Checked at safe boundaries only (see STOP_FILE):
# every remaining step is then skipped and the run still prints its summary, so the user
# sees what did happen rather than the output just ending.
stop_pending() {
    [[ -e "$STOP_FILE" ]] || return 1
    # Only a request made AFTER this run began counts. The run-state file is written the
    # moment the run commits, so it doubles as the run's start stamp — no separate marker
    # needed. Deleting a leftover request at startup instead would race: a stop clicked in
    # the moment before the engine got there would be silently swallowed.
    [[ -e "$RUN_STATE_FILE" && "$STOP_FILE" -nt "$RUN_STATE_FILE" ]] || return 1
    if ! $STOP_HONOURED; then
        STOP_HONOURED=true
        echo
        echo "Stopping at your request — the step that was running has finished, and"
        echo "nothing further will be started."
        marker HINT "Stopped at your request. Anything already installed stays installed — a stop never interrupts an install half-way, because that can leave programs broken. Run the update again whenever you like."
    fi
    return 0
}
begin_step() {
    local key="$1"
    STEP_INDEX=$((STEP_INDEX + 1))
    STEP_START=$SECONDS
    echo
    echo "=========================================="
    printf '  [%d/%d] %s\n' "$STEP_INDEX" "$TOTAL" "${LABEL[$key]}"
    echo "=========================================="
    marker STEP_BEGIN "$key|$STEP_INDEX|$TOTAL|${LABEL[$key]}"
}

end_step() {
    local key="$1" status="$2" detail="${3:-}"
    SECS[$key]=$((SECONDS - STEP_START))
    RESULT[$key]="$status"
    DETAIL[$key]="$detail"
    [[ "$status" == "fail" ]] && ERRORS=$((ERRORS + 1))
    marker STEP_END "$key|$status|$detail"
    # How long the step took, so the GUI can show 'took 42s' on the row. Separate
    # from STEP_END so the existing status|detail contract is untouched.
    marker TIMING "$key|${SECS[$key]}"
}

# Report one step's check result honestly. A count is only trustworthy when we
# could read every source, so when something was unreadable we say so — and we
# withhold a bare zero, because "I couldn't look" rendered as "you're up to date"
# is the one answer an update checker must never give (ONEUP-0056). A count is
# still emitted alongside the warning when we DID find updates: knowing about 7
# of them beats knowing about none while a repository is broken.
emit_check() {  # key, count, label, [what-was-unreadable]
    local key="$1" count="$2" label="$3" unreadable="${4:-}"
    [[ -n "$unreadable" ]] && marker CHECK_UNKNOWN "$key|$unreadable"
    if [[ -z "$unreadable" ]] || (( count > 0 )); then
        marker CHECK "$key|$count|$label"
    fi
}

# ---------------------------------------------------------------------------
# --check: read-only "what would update?" pass. Deliberately avoids root (and a
# password popup) so an unattended timer can run it; it reads cached repo
# metadata and installs nothing. Because it cannot refresh that metadata, it must
# be scrupulous about saying when the metadata isn't there to read.
# ---------------------------------------------------------------------------
run_check() {
    echo "Checking for available updates (read-only)…"
    local total=0 n incomplete=false
    if step_selected system; then
        # Read the upgrade list once: the count AND the per-package detail (name,
        # current → available version) the GUI shows in its expandable preview both
        # come from it. LC_ALL=C keeps the column layout parseable on any locale.
        # stderr is captured WITH stdout rather than discarded: zypper reports a
        # repository it had to set aside as a warning there (and exit 106), and
        # that warning is the only difference between "nothing to update" and
        # "I couldn't read the repository that had the updates". Merging is safe —
        # every line we parse is anchored to zypper's 'v' status column.
        local updates rc unreadable=""
        updates=$(LC_ALL=C zypper --no-refresh --non-interactive list-updates 2>&1)
        rc=$?
        # Upgradable packages have a 'v' in zypper's status column.
        n=$(grep -cE '^v[[:space:]]*\|' <<<"$updates")
        if (( rc != 0 )); then
            # 106 = ZYPPER_EXIT_INF_REPO_SKIPPED. Name the repositories if zypper
            # did; otherwise report the failure without guessing at a cause.
            local skipped
            skipped=$(sed -n "s/.*Skipping repository '\([^']*\)'.*/\1/p" <<<"$updates" \
                      | sort -u | tr '\n' ',' | sed 's/,$//; s/,/, /g')
            if [[ -n "$skipped" ]]; then
                unreadable="OneUp couldn't read these software sources: $skipped"
            else
                unreadable="OneUp couldn't read the software sources (zypper exited $rc)"
            fi
            unreadable+=" — this list may be incomplete. Running an update refreshes them."
            incomplete=true
            echo "  System packages: couldn't check — $unreadable"
        else
            echo "  System packages: $n update(s)"
        fi
        emit_check system "$n" "system package(s)" "$unreadable"
        # Columns: S | Repository | Name | Current | Available | Arch. Trim each
        # field and emit one CHECK_ITEM per package (one awk pass, no per-line fork).
        while IFS='|' read -r name cur avail; do
            [[ -n "$name" ]] && marker CHECK_ITEM "system|$name|$cur|$avail"
        done < <(awk -F'|' '/^v[[:space:]]*\|/ {
                    for (i=3;i<=5;i++) gsub(/^[ \t]+|[ \t]+$/,"",$i); print $3"|"$4"|"$5 }' \
                 <<<"$updates")
        (( total += n ))
    fi
    if step_selected flatpak && command -v flatpak &>/dev/null; then
        # Ask each remote for its own updates. `flatpak remote-ls --updates` with no
        # remote named abandons the WHOLE listing — exit 1, empty stdout — the moment
        # any single remote can't be summarised, and a local `--no-enumerate` origin
        # (what `flatpak install ./app.flatpak` leaves behind) never can be. Measured:
        # six such leftovers on one box hid a real Discord update behind "0" for weeks.
        # Per-remote, one broken source costs only itself. --columns pins the output to
        # app-id + version so count and detail parse the same way on any flatpak build.
        local flatpaks="" scope remote opts rows unreadable=""
        for scope in --user --system; do
            while IFS=$'\t' read -r remote opts; do
                [[ -n "$remote" ]] || continue
                if rows=$(flatpak remote-ls --updates "$scope" "$remote" \
                              --columns=application,version 2>/dev/null); then
                    [[ -n "$rows" ]] && flatpaks+="$rows"$'\n'
                elif [[ "$opts" != *no-enumerate* ]]; then
                    # A no-enumerate origin serves no listing BY DESIGN — apps installed
                    # from a local file have no remote updates to miss, so it is not a
                    # failed check. Any other remote failing means apps went uncounted.
                    unreadable+="${unreadable:+, }$remote"
                fi
            done < <(flatpak remotes "$scope" --columns=name,options 2>/dev/null)
        done
        n=$(grep -c '[^[:space:]]' <<<"$flatpaks")
        if [[ -n "$unreadable" ]]; then
            unreadable="OneUp couldn't reach these Flatpak sources: $unreadable — this list may be incomplete."
            incomplete=true
            echo "  Flatpak apps: couldn't check — $unreadable"
        else
            echo "  Flatpak apps: $n update(s)"
        fi
        emit_check flatpak "$n" "Flatpak app(s)" "$unreadable"
        while read -r app ver _rest; do
            [[ -n "$app" ]] && marker CHECK_ITEM "flatpak|$app||$ver"
        done <<<"$flatpaks"
        (( total += n ))
    fi
    if step_selected firmware && command -v fwupdmgr &>/dev/null; then
        if fwupdmgr get-updates &>/dev/null; then n=1; else n=0; fi
        marker CHECK "firmware|$n|firmware update(s)"
        echo "  Firmware: $( ((n > 0)) && echo available || echo up to date)"
        (( total += n ))
    fi
    marker CHECK "TOTAL|$total|updates available"
    if $incomplete; then
        echo "  Total: $total update(s) found, but at least one source couldn't be read"
        echo "         — treat this as a floor, not an all-clear."
    else
        echo "  Total: $total update(s) available."
    fi
    if $NOTIFY && (( total > 0 )); then
        notify_send "Updates available" \
            "$total update(s) ready to install. Open OneUp to update."
    fi
    marker DONE "ok"
}

# ---------------------------------------------------------------------------
# --size=<step>: on-demand exact download size for one step, for the GUI's "Show
# download size" link. Unlike --check this NEEDS root — it asks the solver (a
# --dry-run of the real transaction) for the total, which zypper won't compute
# unprivileged. Kept separate so the rootless weekly --check stays password-free.
# Mirrors the system step's command so the figure matches what a real run fetches.
# ---------------------------------------------------------------------------
# The transaction argv, stated ONCE (ONEUP-0085 INV-5). Three callers need it — the
# download pass, the commit pass and the --size probe — and a flag added to one and not
# the others would download one set of packages, install a second and quote the size of a
# third, with all three still succeeding. Fills the global SYS_TXN array; not echoed,
# because a command substitution would run it in a subshell.
#
# Defined HERE, above run_size, for the same reason the comment at the --size dispatch
# gives about sudo_init: that dispatch calls run_size and then exits, so anything defined
# further down the file has never been executed and does not exist yet.
system_txn_argv() {
    # BOTH arms take --reposd-dir, or download recovery would be a no-op on Leap while
    # working on Tumbleweed — a retry byte-identical to the attempt that just failed
    # (ONEUP-0094 §4.3). An explicitly-empty array rather than ${VAR:+…}: it keeps a
    # spaced path intact and is safe under `set -u`.
    local -a reposd=()
    [[ -n "$REPOSD_OVERRIDE" ]] && reposd=(--reposd-dir "$REPOSD_OVERRIDE")
    if [[ -f /etc/os-release ]] && grep -q "Leap" /etc/os-release; then
        SYS_TXN=(zypper --non-interactive "${reposd[@]}" update)
    else
        # Tumbleweed: --allow-vendor-change lets Packman codec packages update
        # cleanly; without it the upgrade stalls on vendor conflicts.
        SYS_TXN=(zypper --non-interactive "${reposd[@]}" dup --allow-vendor-change)
    fi
}

run_size() {
    local step="$1" out size rc
    if [[ "$step" != "system" ]]; then
        echo "Download-size preview is only available for the system step." >&2
        return 2
    fi
    sudo_init
    release_zypper_lock
    echo "Calculating download size (dry run)…"
    # sudo_capture, not `out=$(sudo …)`: a substitution can run sudo in a subshell,
    # which re-authenticates and pops a second password box (ONEUP-0037/0038).
    # Same argv the run itself will use (ONEUP-0085 INV-5) — a flag here that the
    # transaction does not have would quote the size of a different transaction.
    system_txn_argv
    sudo_capture -e out env LC_ALL=C "${SYS_TXN[@]}" --dry-run
    rc=$?
    # Two wordings, because zypper renamed this line and OneUp supports both distros:
    #   older (Leap):        "Overall download size: 1.3 GiB. Already cached: 0 B."
    #   current (TW 1.14.98) "Package download size:   371.4 MiB"
    # The current one dropped "Overall"/"Already cached" entirely, which is why a
    # parse for the old wording alone silently reported "nothing to fetch" on a
    # 137-package upgrade. Capture the number+unit (LC_ALL=C above pins '.' as the
    # decimal point, so the value can't run into any trailing sentence).
    size=$(sed -n 's/.*\(Overall\|Package\) download size:[[:space:]]*\([0-9.]\+ [A-Za-z]\+\).*/\2/p' \
        <<<"$out" | head -n1)
    if [[ -n "$size" ]]; then
        marker SIZE "system|$size"
        echo "  Download size: $size"
        size_delivered "$size"
    elif (( rc == 0 )) || (( rc >= 100 && rc <= 103 )); then
        # zypper ran fine and reported no size = nothing to fetch (up to date / all
        # cached). Report zero so the GUI shows a definitive answer. 100-103 are
        # zypper's INFORMATIONAL exits (update/reboot/restart needed) — a non-zero
        # code there is not a failure, so they must not be mistaken for one.
        marker SIZE "system|0 B"
        echo "  Download size: nothing to fetch."
        size_delivered "0 B"
    else
        # The dry run FAILED. Never answer "0 B" here: a confident zero the run
        # didn't earn is the exact failure class the test suite exists to prevent.
        # Stay silent on SIZE and return non-zero — the GUI re-arms its "Show
        # download size" link for a retry (updater.py `_on_size_finished`).
        #
        # Name the real cause from zypper's documented exit codes rather than
        # guessing, and echo the tail of what it actually said: `out` is captured
        # into a variable, so without this the log records only "unavailable" and
        # the user has nothing to act on.
        local why
        case "$rc" in
            7) why="another program is using the package manager (PackageKit, or a zypper you have open elsewhere) — close it and try again." ;;
            5) why="OneUp wasn't allowed to run the check as administrator — the password prompt may have been cancelled." ;;
            6) why="no software sources are enabled, so there is nothing to weigh up." ;;
            *) why="the package manager reported an error (code $rc) — see the lines below." ;;
        esac
        marker HINT "Couldn't work out the download size: $why"
        echo "  Download size: unavailable — $why"
        sed -n 's/^/    zypper: /p' <<<"$out" | tail -n 5
        return 1
    fi
}

# ---------------------------------------------------------------------------
# --hold: keep the --size process alive for the run it just priced (ONEUP-0044).
#
# Why this exists at all: with no terminal, sudo keys its cached credential to the
# PARENT process id, so a preview in one engine and a run in another are two records and
# two password dialogs. Holding one process across both jobs is what makes it one.
# ---------------------------------------------------------------------------

# Close out a successful --size probe. Under --hold the process does NOT end here, so
# the DONE is withheld: the marker reference describes exactly one DONE per run (§4.9),
# and for a run another window merely FOLLOWED through run.state it is "the only verdict
# there is" — two in one stream, the first saying ok before a single step had run, is
# what breaks that reader. A held process emits its DONE at its true end instead. This
# is an ordering change and not a field-layout one, so the §5.1 freeze is untouched.
size_delivered() {
    HOLD_SIZE="$1"
    $HOLD || marker DONE "ok"
}

# Adopt a go-ahead's step list, or refuse the whole thing. Returns 0 only if every key
# resolved and at least one step is selected.
#
# Deliberately STRICTER than --steps=, and reusing that path would be a security defect:
# --steps= iterates the five known keys calling step_selected, so an unknown key is
# silently DROPPED and the only rejection is when every key is unknown. A go.request
# reading "cache,../../evil" would then run the cache step and report success — a file
# the window writes being partly ignored rather than refused. --steps= is a flag a person
# types on their own command line; go.request is an authorisation read by a root process,
# and the two do not warrant the same leniency (ONEUP-0044 §4.6, INV-8).
#
# Membership in LABEL is the check, not a shape test on the characters: a shape check
# passes anything well-formed, where membership of a closed vocabulary is the property
# actually wanted. LABEL is an ASSOCIATIVE array, so the subscript is a literal string —
# an indexed array would arithmetic-evaluate it, which is how a subscript becomes an
# injection point.
adopt_go_ahead() {
    local list="$1" k
    # Named `asked` rather than the obvious `want`: shellcheck's array/string checks are
    # not scope-aware, so declaring a local array called `want` here makes it read
    # `emit_progress`'s unrelated scalar `want` as an array and warn (SC2178/SC2128) on
    # code this change never touched.
    local -a asked=()
    [[ -n "$list" ]] || return 1
    IFS=',' read -r -a asked <<<"$list"
    (( ${#asked[@]} )) || return 1
    for k in "${asked[@]}"; do
        [[ -n "${LABEL[$k]:-}" ]] || return 1
    done
    # Re-derive the selection. Assigning STEPS alone is NOT enough and is the one place
    # this can look right and run the wrong thing: the run path never reads STEPS.
    # step_selected does, but its callers ran long ago — RUN_KEYS, TOTAL, STEP_INDEX and
    # the TOTAL==0 rejection are all derived at script top level, far ABOVE the --size
    # dispatch, and the run loop iterates "${RUN_KEYS[@]}". A go-ahead that only set
    # STEPS would fall through and run whatever startup derived — and request_size passes
    # no --steps=, so that is the default ALL FIVE. The user's "cache" selection would
    # silently become a full system upgrade. INV-6 is what catches this.
    STEPS="$list"
    RUN_KEYS=()
    for k in system flatpak firmware orphans cache; do
        step_selected "$k" && RUN_KEYS+=("$k")
    done
    TOTAL=${#RUN_KEYS[@]}
    STEP_INDEX=0
    (( TOTAL > 0 )) || return 1
}

# Wait for the window's go-ahead. RECORDS a decision; it never runs a step itself — the
# run is straight-line script far below this point (see the comment above
# system_txn_argv: the --size dispatch "calls run_size and then exits", so anything
# further down "has never been executed and does not exist yet"). So a go-ahead returns 0
# and lets the dispatch fall through into the run that already exists.
#
# Returns 0 only on a go-ahead carrying a valid step list. Cancel, a departed window and
# the ceiling all return non-zero — which the caller maps to exit 0, because the job this
# process was started for succeeded and was already reported (§4.4).
hold_for_go_ahead() {
    local waited=0 step=$STOP_POLL_SECONDS rc=1 steps=""
    (( step > 0 )) || step=1
    mkdir -p "$(dirname "$HOLD_STATE_FILE")" 2>/dev/null || true
    # Layout pinned line by line in ONEUP-0044 §4.3, the way run.state's is, so the
    # Python engine can reproduce it: line 1 the engine pid, line 2 the log path
    # verbatim, line 3 the quoted size. Do not reorder or drop a line.
    printf '%s\n%s\n%s\n' "$$" "$LOG_FILE" "$HOLD_SIZE" > "$HOLD_STATE_FILE"
    while (( waited < HOLD_SECONDS )); do
        # Staleness is decided the way stop_pending decides it, and for the same reason:
        # a request older than our own stamp is a leftover from an earlier session.
        # Deleting leftovers at startup instead would race a go-ahead pressed in that
        # very moment — exactly what stop_pending's own comment records.
        if [[ -e "$GO_FILE" && "$GO_FILE" -nt "$HOLD_STATE_FILE" ]]; then
            steps=$(head -n1 "$GO_FILE" 2>/dev/null)
            rc=0
            break
        fi
        # Cancel reuses stop.request — both halves already agree on what it means. But it
        # may NOT be read through stop_pending: that requires run.state to exist and the
        # request to be newer than it, and a hold has deliberately not written run.state,
        # so stop_pending is false for the entire hold and a Cancel wired through it
        # would do nothing for the full ceiling. Compare against our own stamp instead.
        if [[ -e "$STOP_FILE" && "$STOP_FILE" -nt "$HOLD_STATE_FILE" ]]; then
            break
        fi
        kill -0 "$WINDOW_PID" 2>/dev/null || break
        sleep "$step"
        waited=$((waited + step))
    done
    rm -f "$HOLD_STATE_FILE" "$GO_FILE"
    (( rc == 0 )) || return 1
    adopt_go_ahead "$steps"
}

if $CHECK_ONLY; then
    run_check
    exit 0
fi

# ---------------------------------------------------------------------------
# One-time privilege bootstrap: a single labelled KDE password popup, then a
# background keep-alive so later sudo calls reuse the cached credential.
# ---------------------------------------------------------------------------
SUDO_KEEPALIVE=""
sudo_init() {
    # If the ONEUP-0023 passwordless drop-in is active AND grants what this engine needs,
    # every privileged command below is individually NOPASSWD, so no cached credential is
    # needed — and the interactive `sudo -A … -v` here would prompt ANYWAY: sudo's
    # `verifypw` defaults to `all`, so a bare `-v` validate is only password-free when
    # EVERY one of the user's sudoers entries is NOPASSWD (a normal %wheel user's isn't).
    # Skipping it is what lets a headless timer run authenticate.
    #
    # auth_current, not the bare zypper probe: a drop-in from an older OneUp is live and
    # still leaves three calls prompting, and this early return is what turned that into a
    # surprise dialog in the middle of step 1 (ONEUP-0092). Falling through instead costs
    # one labelled prompt up front, which is the honest failure.
    if auth_current; then
        return 0
    fi
    if ! SUDO_ASKPASS="$ASKPASS" sudo -A \
            -p "System Updater: authenticate to update the system" -v; then
        echo "Authentication failed or cancelled — aborting." >&2
        exit 1
    fi
    # Detached from our stdout/stderr so it never pollutes the log stream (and so
    # a consumer capturing our output isn't held open by the keep-alive's sleep).
    # Keep refreshing even if one validation momentarily fails (a transient PAM/cache
    # blip): a single miss must not permanently stop the keeper mid-run. cleanup kills
    # this loop when the script exits, so it never outlives the run.
    #
    # setsid puts the loop in its own process group so cleanup can kill the WHOLE
    # group (kill -- -PGID): a plain `kill $subshell` leaves the inner `sleep 50`
    # orphaned (reparented to init, lingering up to 50s) after a cancelled run.
    # It also watches OUR pid and exits on its own once we're gone. cleanup's group
    # kill is the fast path, but a trap cannot run if the engine is SIGKILLed — and
    # then the loop ran forever: two of them were found still calling `sudo -n -v`
    # every 50 seconds, 40 minutes after the runs that spawned them were killed
    # (ONEUP-0041). $0 carries a grep-able tag so a test can identify these without
    # matching every `sleep 50` on the machine.
    # shellcheck disable=SC2016  # the single quotes are the point: "$1" must reach the
    # INNER shell unexpanded, where it is the engine pid passed as an argument below.
    setsid bash -c '
        while kill -0 "$1" 2>/dev/null; do
            sudo -n -v 2>/dev/null || true
            sleep 50
        done' oneup-keepalive "$$" >/dev/null 2>&1 &
    SUDO_KEEPALIVE=$!
}

# Capture a privileged command's output without letting sudo re-authenticate:
#
#     sudo_capture [-e] VAR cmd [args…]      # -e also captures stderr
#
# With no terminal — the GUI runs us through QProcess — sudo keys its cached
# credential to the PARENT PROCESS ID (sudoers(5) `timestamp_type`: the `tty`
# default falls back to the ppid when no terminal is present). Bash forks a real
# subshell for `$(cmd | other)`, `$(a; b)`, `$(cmd "$(nested)")` and `< <(cmd |
# other)`, so a sudo inside one has a *different* parent and is authenticated
# separately — one extra KDE password popup per call site, worded in sudo's own bare
# "password for root" (ONEUP-0038: a full run asked seven times).
#
# Redirecting to a temp file we own keeps sudo in the caller's own shell, so
# sudo_init's single up-front prompt covers the whole run. Rule for new code: run
# the privileged command through this helper, then do the text processing on the
# captured text (`awk … <<<"$var"`) — never in a pipeline wrapped around sudo.
sudo_capture() {
    local _cap_err=false
    [[ "$1" == "-e" ]] && { _cap_err=true; shift; }
    local -n _cap_var="$1"; shift
    local _cap_tmp _cap_rc
    _cap_tmp=$(mktemp) || return 1
    # shellcheck disable=SC2024  # "sudo doesn't affect redirects" isn't a problem
    # here: $_cap_tmp is our own mktemp file, so writing it as the normal user is
    # exactly right. shellcheck's suggested `| sudo tee` would put sudo back inside
    # a pipeline subshell and reintroduce the extra password prompt.
    if $_cap_err; then
        sudo "$@" > "$_cap_tmp" 2>&1
    else
        sudo "$@" > "$_cap_tmp" 2>/dev/null
    fi
    _cap_rc=$?
    _cap_var=$(<"$_cap_tmp")     # no sudo here, so no second credential lookup
    rm -f "$_cap_tmp"
    return $_cap_rc
}
# Negative PID targets the keep-alive's process group (the loop shell + its sleep),
# so nothing survives the run. See sudo_init for why setsid makes this a lone group.
# Re-enable every repo we disabled BEFORE killing the keep-alive (sudo cred still
# warm), non-interactively (-n) so a cold-credential exit logs the manual fix
# instead of blocking on a ksshaskpass popup inside the trap.
# An askpass helper whose sudo has gone is a password dialog nobody is waiting on — it
# just sits on the user's screen. Eleven had piled up on the reporter's machine, and one
# was still open 5.7 hours after its run had finished and exited cleanly, which is a
# large part of why "three prompts in a row" felt like more than three. Only processes
# that are BOTH orphaned (parent pid 1) and carrying one of OUR prompts are touched, so
# a live dialog that another OneUp process is still waiting on is never killed. Why a
# duplicate gets raised in the first place is still unexplained — see ONEUP-0043.
reap_orphaned_askpass() {
    local pid ppid args pcmd
    while read -r pid ppid args; do
        # Both the helper's path AND one of our own prompts must appear: the path alone
        # would catch another app's dialog, a prompt alone could match an unrelated
        # process that merely mentions the text. Matched as substrings rather than a
        # leading path because a script helper is shown by ps as "bash <script> …".
        case "$args" in *"$ASKPASS"*) ;; *) continue ;; esac
        case "$args" in
            *"$SUDO_PROMPT"*|*"System Updater: authenticate to update the system"*) ;;
            *) continue ;;
        esac
        # A dialog someone IS waiting on is a child of the sudo that launched it, so the
        # parent's command line is the test. Deliberately not "parent is pid 1": under
        # systemd a user session's orphans are reparented to `systemd --user`, not init,
        # so an orphan-check against pid 1 silently never fires (measured — it was the
        # first version of this function and it reaped nothing).
        pcmd=$(tr '\0' ' ' < "/proc/$ppid/cmdline" 2>/dev/null)
        [[ "$pcmd" == *sudo* ]] && continue
        kill "$pid" 2>/dev/null
    done < <(ps -eo pid=,ppid=,args= 2>/dev/null)
}
RUN_STATE_OWNED=false      # only the process that wrote the run-state file clears it,
                           # so a --check or --size run can't erase a real run's entry
cleanup() {
    local a
    $RUN_STATE_OWNED && rm -f "$RUN_STATE_FILE" "$STOP_FILE"
    reap_orphaned_askpass
    for a in "${DISABLED_REPOS[@]:-}"; do
        [[ -z "$a" ]] && continue
        sudo -n zypper --non-interactive modifyrepo --enable "$a" >/dev/null 2>&1 \
            || echo "  ! Couldn't re-enable repository '$a' — run: sudo zypper modifyrepo --enable $a" >&2
    done
    [[ -n "$SUDO_KEEPALIVE" ]] && kill -- "-$SUDO_KEEPALIVE" 2>/dev/null
}
# EXIT runs cleanup on any exit (killing the keep-alive so it can't outlive the run).
# The signal traps must ALSO exit: a plain `trap cleanup INT` would run cleanup and
# then resume after the interrupted command, plowing on through the remaining
# privileged steps the user just tried to cancel. Exiting fires the EXIT trap, so
# cleanup still runs. 130 = 128+SIGINT, 143 = 128+SIGTERM (conventional exit codes).
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
# 141 = 128+SIGPIPE. Only reachable on a `tee` without -p (see the logging block): the
# point is that cleanup still runs — an untrapped SIGPIPE kills the shell outright and
# leaves the keep-alive looping and disabled repos disabled.
trap 'exit 141' PIPE

# ---------------------------------------------------------------------------
# Free the zypper lock. The desktop's background updater (PackageKit) grabs the
# package lock shortly after login to check for updates; while it holds the lock
# every `zypper` call below is refused ("System management is locked by ...
# packagekitd"). We stop the daemon so our steps can take the lock — it is
# D-Bus/socket-activated and restarts on its own the next time the desktop needs
# it, so nothing is left disabled.
# ---------------------------------------------------------------------------
release_zypper_lock() {
    if systemctl is-active --quiet packagekit 2>/dev/null; then
        echo "Stopping the desktop updater (PackageKit) so it isn't holding the package lock..."
        sudo systemctl stop packagekit 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# Whoever else holds the package lock (ONEUP-0039). One busy program makes every
# zypper step below fail for the same uninteresting reason, and zypper says so only
# in its own words: "System management is locked by the application with pid 447150
# (zypper)". A user hit exactly that after quitting OneUp mid-download — the engine's
# own zypper kept installing in the background (deliberately: killing a transaction
# half-way can break the package database), so the next run reported five failures
# whose single cause was "OneUp is already busy".
#
# libzypp records the holder's pid in /run/zypp.pid, which is world-readable, so we
# can name it before touching anything. Overridable so tests never need real /run.
# ---------------------------------------------------------------------------
ZYPP_PID_FILE="${ONEUP_ZYPP_PID_FILE:-/run/zypp.pid}"
lock_holder() {          # echoes "<pid> <name>" of the process holding the lock
    local pid name
    [[ -r "$ZYPP_PID_FILE" ]] || return 1
    read -r pid _ < "$ZYPP_PID_FILE" 2>/dev/null || return 1
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    # A pid with no /proc entry is a stale lock from a crashed run, not a live
    # holder — zypper clears it itself, so it must not block us.
    [[ -d "/proc/$pid" ]] || return 1
    (( pid == $$ )) && return 1
    name=$(cat "/proc/$pid/comm" 2>/dev/null)
    echo "$pid ${name:-another program}"
}

# ---------------------------------------------------------------------------
# Opt-in "remember my authorization" mode (ONEUP-0023). Deliberately stores NO
# password — encrypting a password the app must itself decrypt is obfuscation,
# and a stored root password would break OneUp's "GUI never touches root" design.
# Instead we install a scoped, revocable sudoers drop-in so the OS remembers the
# *decision* (for OneUp's update commands only), not the password. Toggle off =
# delete the file = instant, complete revoke.
#
# This is effectively passwordless root for those commands (zypper can run
# arbitrary code via package scripts), which is why it is opt-in, off by default,
# and the GUI shows an explicit warning before enabling it.
#
# Overridable so the test suite points it at a throwaway path, never real /etc.
AUTH_FILE="${ONEUP_AUTH_FILE:-/etc/sudoers.d/oneup}"

# The granted scope, written in ONE place (ONEUP-0092). Echoes the comma-joined Cmnd list.
# Built from the binaries actually present on THIS machine (command -v, not a hardcoded
# /usr/bin) so each rule matches the exact path sudo will resolve. zypper is required; the
# optional ones are skipped when absent.
auth_cmnds() {
    local zypper cmd cmds=()
    zypper=$(command -v zypper) || return 1
    cmds+=("$zypper")                                   # any zypper subcommand
    cmd=$(command -v snapper)   && cmds+=("$cmd")        # snapper create/list
    cmd=$(command -v flatpak)   && cmds+=("$cmd")        # flatpak update/uninstall
    cmd=$(command -v systemctl) && cmds+=("$cmd stop packagekit")
    # The engine pins the locale via `sudo env LC_ALL=C zypper …`. sudo resolves the
    # command (env) to a path but matches the REST of the argv literally, so this
    # pattern's second word must be the bare `zypper` the engine typed, not its path.
    cmd=$(command -v env)       && cmds+=("$cmd LC_ALL=C zypper *")
    # The three ONEUP-0092 entries. Empty means `command -v` failed at file scope, where a
    # failure leaves an empty element rather than a non-zero status — so test the element,
    # never the substitution. Emitting a bare name here would make visudo reject the file.
    [[ -n "${REFRESH_SUDO_ARGV[0]}" && -n "${CACHE_DU_ARGV[0]}" ]] || return 1
    # The budget lands in the one slot a wildcard would make exploitable, and it arrives
    # from the environment ($ONEUP_REFRESH_TIMEOUT), so it is pinned to digits here rather
    # than trusted: `5 *` would generate `timeout 5 * zypper *`, which visudo accepts and
    # which `timeout 5 /bin/sh -c 'zypper x'` then satisfies.
    [[ "${REFRESH_SUDO_ARGV[1]}" =~ ^[0-9]+$ ]] || return 1
    cmds+=("${REFRESH_SUDO_ARGV[*]} *")                 # timeout <budget> zypper …
    cmds+=("${CACHE_DU_ARGV[*]}")                       # du -sB1 /var/cache/zypp, exactly
    cmds+=("$GUARD_FILE")                               # any args: the guard restricts itself
    local joined
    printf -v joined '%s, ' "${cmds[@]}"
    echo "${joined%, }"
}

# The download guard's text — the single source, and the same bytes that get installed.
# Compared byte-for-byte by guard_current, so every edit here re-grants for every user.
download_guard_src() {
    local zypper scope
    zypper=$(command -v zypper) || return 1
    scope=$(auth_cmnds) || return 1
    # `# oneup-auth-scope:` is what makes this file a version stamp for the drop-in beside
    # it: the drop-in is 0440 root-only, so the engine cannot read back what it granted,
    # but both files are written by the same grant and this one is world-readable.
    cat <<EOF
#!/bin/bash
# Installed by OneUp's "remember my authorization" setting (ONEUP-0092). Runs the package
# download as root so a Stop request can reach zypper, which an unprivileged parent cannot
# signal. It can exec exactly one program — the zypper below — so granting it in sudoers
# grants no more than the drop-in's own zypper entry.
# Delete it (or turn the setting off in OneUp) to revoke.
# oneup-auth-scope: $scope
export LC_ALL=C
stop_file="\$1"; run_state="\$2"; poll="\$3"
[[ "\$4" == zypper ]] || { echo "oneup-download-guard: refusing to run '\$4'" >&2; exit 2; }
shift 4
"$zypper" "\$@" --download-only &
z=\$!
while kill -0 "\$z" 2>/dev/null; do
    # Same staleness rule as stop_pending: a request older than run.state is a leftover.
    # Re-implemented because a shell function cannot cross sudo.
    if [[ -e "\$stop_file" && -e "\$run_state" && "\$stop_file" -nt "\$run_state" ]]; then
        kill -TERM "\$z" 2>/dev/null
        break
    fi
    sleep "\$poll"
done
wait "\$z"        # never exit without reaping — an unreaped root child is the
exit \$?          # ONEUP-0041 orphan shape, one level down
EOF
}

# Is the installed guard the one THIS engine expects? A pure file comparison — no sudo, so
# it is safe to call mid-run, which is why run_system_download asks this rather than
# auth_current. (Command substitution strips trailing newlines on both sides, so this
# compares the text rather than the bytes; nothing else differs.)
guard_current() {
    [[ -r "$GUARD_FILE" ]] && [[ "$(<"$GUARD_FILE")" == "$(download_guard_src)" ]]
}

# Is passwordless actually working for THIS engine? Both halves are needed: the drop-in is
# live, AND it grants what this run needs. The old check asked only the first question of
# one command out of six, which is how ONEUP-0092's three uncovered calls went unseen.
auth_current() {
    local zypper
    zypper=$(command -v zypper) || return 1
    # `-k` ignores any cached credential (so a recent run can't false-positive) and `-n`
    # refuses to prompt. Measured: -k does NOT invalidate a warm credential, so this is
    # safe to issue at any point in a run.
    sudo -k -n "$zypper" --version >/dev/null 2>&1 || return 1
    guard_current
}

build_auth_rule() {
    local user cmnds
    user=$(id -un)
    cmnds=$(auth_cmnds) || return 1     # split assignment: `local x=$(…)` masks the status
    cat <<EOF
# Installed by OneUp's "remember my authorization" setting — stores NO password.
# Lets $user run OneUp's update commands as root without a password prompt.
# Delete this file (or turn the setting off in OneUp) to revoke immediately.
Cmnd_Alias ONEUP_UPDATE = $cmnds
$user ALL=(root) NOPASSWD: ONEUP_UPDATE
EOF
}

# The order below is fixed and each step's position is load-bearing (ONEUP-0092 §4.3):
# validate FIRST so a malformed rule costs nothing, then the guard, then the drop-in — and
# any failure after the guard lands removes it again. A stranded root-owned executable is
# worse than a failed grant: afterwards the toggle reads off, which makes the GUI's revoke
# arm unreachable, so the user has consented to a file they can no longer withdraw.
grant_auth() {
    local tmp guard
    tmp=$(mktemp) || { marker HINT "Could not create a temporary file."; return 1; }
    guard=$(mktemp) || { rm -f "$tmp"; marker HINT "Could not create a temporary file."; return 1; }
    if ! build_auth_rule > "$tmp" || ! download_guard_src > "$guard"; then
        rm -f "$tmp" "$guard"
        marker HINT "Passwordless authorization can't be set up on this machine: zypper, timeout or du was not found, or the refresh budget is not a whole number of seconds."
        return 1
    fi
    sudo_init
    # Validate the generated rule in isolation BEFORE it can affect the live policy:
    # a syntactically broken file under /etc/sudoers.d can lock you out of sudo.
    if ! sudo visudo -cf "$tmp" >/dev/null 2>&1; then
        rm -f "$tmp" "$guard"
        marker HINT "The generated authorization rule failed validation — nothing was changed."
        return 1
    fi
    # 0755: the GUI and the engine both read it back to tell whether the drop-in beside it
    # is the one this OneUp needs, and only root may write it.
    if ! sudo install -o root -g root -m 0755 "$guard" "$GUARD_FILE"; then
        rm -f "$tmp" "$guard"
        marker HINT "Could not write the download helper ($GUARD_FILE)."
        return 1
    fi
    # install(1) atomically places it root-owned and 0440, the mode sudo requires.
    if ! sudo install -o root -g root -m 0440 "$tmp" "$AUTH_FILE"; then
        rm -f "$tmp" "$guard"
        sudo rm -f "$GUARD_FILE"     # never leave the guard behind without its rule
        marker HINT "Could not write the authorization rule ($AUTH_FILE)."
        return 1
    fi
    rm -f "$tmp" "$guard"
    echo "Passwordless authorization for OneUp's update commands is now enabled."
    marker AUTH "on"
}

revoke_auth() {
    sudo_init
    # Both candidate guard paths, not just today's: GUARD_DIR is recomputed per run, so a
    # /usr/libexec created by another package after the grant would move it and leave the
    # /usr/lib copy beyond reach. When ONEUP_GUARD_FILE is set the sweep collapses to that
    # one path — the override exists so the suite never touches a real system directory.
    local -a guards=("$GUARD_FILE")
    [[ -z "${ONEUP_GUARD_FILE:-}" ]] && guards=(/usr/libexec/oneup-download-guard /usr/lib/oneup-download-guard)
    if sudo rm -f "$AUTH_FILE" "${guards[@]}"; then
        echo "Passwordless authorization has been revoked."
        marker AUTH "off"
    else
        marker HINT "Could not remove the authorization rule ($AUTH_FILE)."
        return 1
    fi
}

auth_status() {
    # "on" means passwordless WORKS for this engine, not merely that a rule exists: a
    # drop-in installed by an older OneUp is live and still leaves a run prompting
    # (security.md §5.6 — report real state, never a saved preference).
    if auth_current; then
        marker AUTH "on"
    else
        marker AUTH "off"
    fi
}

# --thin-snapshots: reclaim disk by removing expendable Btrfs snapshots. Uses
# snapper's OWN cleanup algorithms (number/timeline), which only drop snapshots the
# configured retention policy already considers surplus — we never hand-delete a
# specific one, so the most recent rollback points are always kept. Reports the
# before/after count so the GUI can confirm what was tidied.
thin_snapshots() {
    if ! command -v snapper &>/dev/null; then
        marker HINT "Snapper isn't installed, so there are no snapshots to thin."
        return 0
    fi
    sudo_init
    local before after list
    sudo_capture list snapper --no-headers list
    before=$(grep -c . <<<"$list")
    sudo snapper cleanup number   2>&1 || true
    sudo snapper cleanup timeline 2>&1 || true
    sudo_capture list snapper --no-headers list
    after=$(grep -c . <<<"$list")
    if [[ "$before" =~ ^[0-9]+$ && "$after" =~ ^[0-9]+$ ]] && (( before > after )); then
        echo "Thinned $(( before - after )) old snapshot(s) ($before → $after)."
        marker SNAPSHOTS "thinned|$(( before - after ))"
    else
        echo "No snapshots needed thinning — snapper's retention policy is already satisfied."
        marker SNAPSHOTS "thinned|0"
    fi
}

if [[ -n "$AUTH_ACTION" ]]; then
    case "$AUTH_ACTION" in
        grant)      grant_auth ;;
        revoke)     revoke_auth ;;
        status)     auth_status ;;
        emit-guard) download_guard_src ;;
    esac
    exit $?
fi

if $THIN_SNAPSHOTS; then
    thin_snapshots
    exit $?
fi

# --size=<step>: report the download size and exit, never falling through into a
# real update. Placed here so run_size can reuse sudo_init/release_zypper_lock,
# both of which are now defined.
if [[ -n "$SIZE_STEP" ]]; then
    run_size "$SIZE_STEP"
    size_rc=$?
    if $HOLD && (( size_rc == 0 )); then
        # --hold: a go-ahead returns 0 and we fall THROUGH into the run below, reusing
        # the credential this process already cached — which is the whole fix.
        #
        # Anything else ends the process, and ends it with status 0. Expiry, Cancel and a
        # departed window are not failures: the job this process was started for — quoting
        # the size — succeeded and was already reported, so a user running --size --hold
        # in a terminal must not see a failure for a run they simply chose not to start.
        # The window re-arms, Update starts a fresh engine, and the user gets today's
        # behaviour and today's two prompts: the fix degrades to the status quo rather
        # than to an error (§4.4, INV-7). The DONE withheld by size_delivered is emitted
        # here, at this process's true end, so the stream still carries exactly one.
        if hold_for_go_ahead; then
            HELD_AUTH=true
        else
            marker DONE "ok"
            exit 0
        fi
    else
        exit $size_rc
    fi
fi

# Firmware uses polkit for its own elevation; every other root step reuses the
# cached sudo credential, so we only bootstrap when a sudo step is selected.
needs_sudo=false
for k in system flatpak orphans cache; do
    step_selected "$k" && needs_sudo=true
done
# A held preview already authenticated in THIS process, and sudo_init has no re-entry
# guard: its only early return is auth_current, which is false for precisely the users
# this fix is for. Re-entering it would re-run the interactive validate AND spawn a
# second keep-alive, overwriting SUDO_KEEPALIVE so cleanup's group kill can only reach
# the later group — the orphaned-keep-alive leak of ONEUP-0041 (security.md §2.4). Every
# other sudo_init call site sits in a dispatch block that exits, so the held path is the
# first thing in this engine that could reach two of them. INV-9 pins it.
# release_zypper_lock below is re-entered harmlessly and is deliberately left alone.
if $needs_sudo && ! $HELD_AUTH; then
    sudo_init
fi

# With the credential warm, make sure PackageKit isn't sitting on the lock.
$needs_sudo && release_zypper_lock

# Stopping PackageKit clears the common case; anything ELSE still holding the lock
# would make every zypper step fail for one reason, so say that reason once and stop
# rather than taking a snapshot and reporting a pile of failures (ONEUP-0039). Only
# the zypper-backed steps care — a Flatpak- or firmware-only run is unaffected.
needs_zypper=false
for k in system orphans cache; do
    step_selected "$k" && needs_zypper=true
done
if $needs_zypper && holder=$(lock_holder); then
    holder_pid=${holder%% *}; holder_name=${holder#* }
    echo "The package manager is busy: $holder_name (process $holder_pid) is using it."
    echo "Nothing has been changed. Try again once it has finished."
    marker HINT "Something else is installing or removing software right now — $holder_name (process $holder_pid). That is often OneUp's own earlier run still finishing in the background; it clears on its own. Nothing was changed, so just run the update again in a minute."
    marker DONE "errors"
    exit 1
fi

# From here the run is definitely going ahead, so record it. A GUI starting up can then
# find a run already in flight — they outlive the window on purpose (ONEUP-0042) — and
# follow this log rather than offering a Run button that could only fail on the lock.
mkdir -p "$(dirname "$RUN_STATE_FILE")" 2>/dev/null
printf '%s\n%s\n%s\n%s\n' "$$" "$LOG_FILE" "$STEPS" "$(date +%s)" > "$RUN_STATE_FILE" \
    && RUN_STATE_OWNED=true
# A stop request older than the line above is a leftover and is ignored by stop_pending;
# cleanup deletes it on the way out so it can't confuse anything later.

# ---------------------------------------------------------------------------
# Pre-update snapshot note (btrfs/snapper rollback point). Read-only: Tumbleweed
# already auto-snapshots around zypper; we just surface the latest id so the log
# records a rollback target.
# ---------------------------------------------------------------------------
if step_selected system && command -v snapper &>/dev/null; then
    # Create a clearly-labelled rollback point so the pre-update state is easy to
    # find later. (Tumbleweed also auto-snapshots around zypper, but a named entry
    # is unambiguous.) Fall back to reporting the newest snapshot if create fails.
    # The description is built FIRST: a nested `$(date …)` inside the capture would
    # fork a subshell and cost an extra password prompt (see sudo_capture).
    SNAP_DESC="OneUp pre-update $(date '+%Y-%m-%d %H:%M')"
    sudo_capture SNAP_ID snapper create --description "$SNAP_DESC" \
        --cleanup-algorithm number --print-number
    if [[ -z "$SNAP_ID" ]]; then
        sudo_capture SNAP_LIST snapper --no-headers list
        SNAP_ID=$(tail -n1 <<<"$SNAP_LIST" | awk '{print $1}')
    fi
    if [[ -n "$SNAP_ID" ]]; then
        echo "Pre-update snapshot #$SNAP_ID recorded  (roll back with: sudo snapper rollback $SNAP_ID)"
        marker SNAPSHOT "$SNAP_ID"
    fi
    # ONEUP-0020: enumerate the most recent restore points so the GUI's rollback
    # dialog can offer a picker, not just the pre-update snapshot. Read-only.
    # Machine-readable CSV keeps the date ISO-clean and quotes any comma in a
    # description; we skip snapshot 0 (the live "current" pseudo-entry, which has
    # no date and isn't a rollback target) and keep only the newest 12. Only the
    # id is trusted downstream (the GUI re-validates it as a bare number before it
    # reaches snapper); the date/description are display-only.
    sudo_capture SNAP_CSV snapper --machine-readable csv list \
        --columns number,date,description
    awk -F',' 'NR>1 && $1 ~ /^[0-9]+$/ && $1 != "0" && $2 != "" {
              desc = $0; sub(/^[^,]*,[^,]*,/, "", desc)   # everything after the 2nd comma
              gsub(/^"|"$/, "", desc); gsub(/\|/, "/", desc)
              print $1 "|" $2 "|" desc
          }' <<<"$SNAP_CSV" \
        | tail -n 12 \
        | while IFS='|' read -r snum sdate sdesc; do
              marker SNAPSHOT_ITEM "$snum|$sdate|$sdesc"
          done
fi

# ---------------------------------------------------------------------------
# Pre-flight checks (read-only): warn about low disk space and unhealthy repos
# BEFORE changing anything, so a run can't die half-way through a transaction.
# ---------------------------------------------------------------------------
if step_selected system; then
    # Disk: an interrupted transaction from a full disk is the worst failure mode.
    for mp in / /var; do
        avail=$(df -PB1 "$mp" 2>/dev/null | awk 'NR==2{print $4}')
        if [[ -n "$avail" ]] && (( avail < 2 * 1024 * 1024 * 1024 )); then
            human=$(numfmt --to=iec "$avail" 2>/dev/null || echo "${avail}B")
            echo "  ! Low disk space on $mp: only $human free (recommend at least 2 GiB)."
            marker DISK "warn|$mp|$human"
        fi
    done
    # Btrfs snapshots: Tumbleweed takes a pre/post snapshot pair around every zypper
    # transaction, so restore points accumulate and can quietly fill the root
    # filesystem. We're already root here, so count them and, when a lot have piled
    # up, surface a dismissible heads-up + the one-click "thin them" remedy. Count is
    # the honest signal: Btrfs shares extents copy-on-write, so a byte figure would
    # overcount, and per-snapshot quota data is usually off on the root config.
    if command -v snapper &>/dev/null; then
        sudo_capture SNAP_LIST snapper --no-headers list
        snap_count=$(grep -c . <<<"$SNAP_LIST")
        if [[ "$snap_count" =~ ^[0-9]+$ ]] && (( snap_count >= SNAP_WARN_COUNT )); then
            echo "  ! $snap_count system restore points (snapshots) stored — these build up"
            echo "    with each update and can use a lot of disk space; consider thinning them."
            marker SNAPSHOTS "warn|$snap_count"
        fi
    fi
    # Repos: duplicate repository URLs are a frequent source of update conflicts.
    dupe=$(zypper --non-interactive lr -u 2>/dev/null \
        | awk -F'|' 'NF>=6{u=$NF; gsub(/ /,"",u); if(u!="" && u!="URI") c[u]++} END{for(k in c) if(c[k]>1) print k}')
    if [[ -n "$dupe" ]]; then
        echo "  ! Duplicate repository URL(s) detected — a common cause of conflicts:"
        echo "$dupe" | sed 's/^/      /'
        # Pass the actual URL(s) to the GUI so its banner can name the culprit
        # (URLs never contain spaces, so a space-join survives the single marker line).
        dupe_flat=$(echo "$dupe" | tr '\n' ' ' | sed 's/ *$//')
        marker REPO "warn|duplicate|$dupe_flat"
    fi
fi

# ---------------------------------------------------------------------------
# Repo resilience: set a broken source aside instead of failing the whole run.
# ---------------------------------------------------------------------------
valid_alias() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9:@._+-]*$ ]]; }

disable_repo() {   # $1=alias $2=reason ; records + marks on success, fail-closed
    local alias="$1" reason="$2"
    valid_alias "$alias" || { echo "  Refusing unsafe repo alias: $alias" >&2; return 1; }
    if sudo zypper --non-interactive modifyrepo --disable "$alias" >/dev/null 2>&1; then
        DISABLED_REPOS+=("$alias"); marker REPO_SKIPPED "$alias|$reason"; return 0
    fi
    return 1
}

enabled_repo_aliases() {   # alias of each ENABLED repo (read-only; no root)
    LC_ALL=C zypper --non-interactive lr -u 2>/dev/null | awk -F'|' '
        { for (i=1;i<=NF;i++) gsub(/^ +| +$/,"",$i) }
        $1 ~ /^[0-9]+$/ && tolower(substr($4,1,1))=="y" { print $2 }'
}

# Fills FAILING_REPOS[] with "alias reason" per enabled repo that fails its own
# refresh. It fills a global instead of echoing on purpose: the caller used to read
# it through `< <(find_failing_repos)`, which runs the whole function — and its
# privileged refreshes — in a subshell, costing an extra password prompt (see
# sudo_capture). Nothing here may sit inside a substitution.
FAILING_REPOS=()
find_failing_repos() {
    local alias out rc reason
    local -a aliases=()
    mapfile -t aliases < <(enabled_repo_aliases)   # read-only, no sudo inside
    FAILING_REPOS=()
    for alias in "${aliases[@]}"; do
        [[ -z "$alias" ]] && continue
        sudo_capture -e out zypper --non-interactive refresh "$alias"; rc=$?
        (( rc == 0 )) && continue
        if   grep -qiE 'signature|GPG|key' <<<"$out"; then reason=signature
        elif grep -qiE 'metadata|Valid metadata not found' <<<"$out"; then reason=metadata
        else reason=unreachable; fi
        FAILING_REPOS+=("$alias $reason")
    done
}

repo_scoped_failure() {
    grep -qiE 'signature|GPG|key|metadata|Valid metadata not found|Curl|could not resolve|Download.*failed|Skipping repository' "$SYS_LOG"
}

# Refresh each enabled repository on its own, with its own time budget, instead of one
# bulk `zypper refresh` (ONEUP-0048). Three things that buys us, all of them things a
# bulk refresh cannot give:
#
#   * a name — @@REFRESH@@ says WHICH source is being fetched, and how far through the
#     list we are. Bulk refresh reports progress as undelimited dots with no newline, so
#     a line-based reader (the GUI) draws nothing at all for the whole phase.
#   * an escape — zypper has no timeout, so a mirror serving an 18 MB index at 1 KB/s
#     hangs the run for hours. `sudo timeout` runs timeout AS ROOT so it can actually
#     kill its zypper child; we then carry on from cached metadata, which the caller
#     already reports honestly as "upgraded from cached metadata".
#   * a stop — the request is checked between repositories, so Stop works during the
#     longest phase of the run. Free here, because nothing has been installed yet.
#
# The sudo stays a top-level command of THIS shell — never inside a subshell or a
# backgrounded pipeline — so it reuses sudo_init's one credential (see sudo_capture).
REFRESH_FAILED=false
# Whether this run has refreshed the repositories yet. A later step needs to tell fresh
# metadata from stale without paying for a second refresh — see the orphans step, which
# is reached with this still false whenever the system step was not selected.
REPOS_REFRESHED=false
refresh_repos() {
    REPOS_REFRESHED=true
    local -a aliases=() gpg=()
    mapfile -t aliases < <(enabled_repo_aliases)   # read-only, no sudo inside
    local total=${#aliases[@]} i=0 alias rc
    # The user approved importing repository signing keys for this run (--import-keys).
    $IMPORT_KEYS && gpg=(--gpg-auto-import-keys)
    if (( total == 0 )); then
        # The repository list is only available by parsing zypper's own table, so it can
        # come back empty (an unexpected format, a machine with none configured). Fall
        # back to one bulk refresh: upgrading from stale metadata because we quietly
        # skipped the refresh is far worse than losing the per-source progress.
        sudo zypper --non-interactive "${gpg[@]}" refresh || REFRESH_FAILED=true
        return 0
    fi
    for alias in "${aliases[@]}"; do
        [[ -z "$alias" ]] && continue
        i=$((i+1))
        stop_pending && return 0
        marker REFRESH "$i|$total|$alias"
        sudo "${REFRESH_SUDO_ARGV[@]}" --non-interactive "${gpg[@]}" refresh "$alias"
        rc=$?
        (( rc == 0 )) && continue
        # 124 is timeout's "I killed it" — a slow server, not a broken repository, so say
        # so in those words and offer the skip the GUI already knows how to apply. The
        # repo is NOT disabled here: we simply could not refresh it this run.
        if (( rc == 124 )); then
            echo "  Gave up on '$alias' after ${REFRESH_TIMEOUT}s — its server is too slow right now."
            marker HINT "The '$alias' source is serving updates too slowly to wait for, so OneUp moved on. Use \"Skip $alias & update the rest\" to leave it out of the next run, or try again later."
            marker REMEDY "skip-repo|$alias"
        fi
        REFRESH_FAILED=true
    done
    return 0
}

# Turn zypper's own per-package chatter into progress markers, so a long download or
# install can never look like a hang (ONEUP-0040). A user quit a run that was working
# perfectly — it was several minutes into fetching 379 MiB with nothing on screen but
# zypper's dots — and the orphaned transaction then blocked the next two runs.
#
# zypper's three phases, verbatim (LC_ALL=C is pinned on the transaction, so these
# strings are stable on a non-English desktop too):
#
#   Preloading: libglfw3-3.4-67.34.x86_64.rpm [done]
#   Retrieving: cpupower-lang-7.1.4-17.noarch (devel-tools) (1/77),  31.0 KiB
#   ( 1/77) Installing: cpupower-lang-7.1.4-17.noarch [...done]
#
# Only the last two carry a total. The preload — the parallel prefetch, and the phase
# the user actually sat through — has no counter, so it reports a total of 0 meaning
# "unknown" and the GUI shows a live tally instead of inventing a denominator.
# "31.0 KiB" -> 31744. Integer arithmetic only, because bash has no floats: zypper
# prints one decimal place, so scale by ten and divide back down.
to_bytes() {             # number, unit -> whole bytes on stdout (0 if unparsable)
    local n="$1" u="$2" whole frac mult
    whole=${n%%.*}
    frac=${n#*.}; [[ "$frac" == "$n" ]] && frac=0    # no decimal point at all
    frac=${frac:0:1}
    [[ "$whole" =~ ^[0-9]+$ && "$frac" =~ ^[0-9]$ ]] || { echo 0; return 0; }
    case "$u" in
        B)   mult=1 ;;
        KiB) mult=1024 ;;
        MiB) mult=1048576 ;;
        GiB) mult=1073741824 ;;
        *)   echo 0; return 0 ;;
    esac
    # 10# so a zero-padded figure is read as decimal, not as an invalid octal literal.
    echo $(( (10#$whole * 10 + 10#$frac) * mult / 10 ))
}
emit_progress() {        # step-key, "n/m" (zypper pads it: "( 1/77)"), phase, [bytes-so-far], [bytes-total]
    local step="$1" frac="${2// /}" phase="$3" got="${4:-}" want="${5:-}"
    # Non-zero when there was no counter to parse, so the caller can tell "emitted" from
    # "skipped" — that distinction is what the stale-parser canary below relies on.
    [[ "$frac" =~ ^([0-9]+)/([0-9]+)$ ]] || return 1
    local payload="$step|${BASH_REMATCH[1]}|${BASH_REMATCH[2]}|$phase"
    # The byte fields are optional: only the download phase can count them, and only
    # once zypper has printed a size. A total of 0 means "not known yet".
    [[ -n "$got" ]] && payload+="|$got|${want:-0}"
    marker PROGRESS "$payload"
}
PROGRESS_SEEN_FILE=""    # progress_filter runs as a pipeline element, i.e. in a subshell,
                         # so it reports back through a file rather than a variable
progress_filter() {      # step-key [phase]; passes every line through, adding @@PROGRESS@@
    # `phase` is which pass we are filtering — "download" or "install" (ONEUP-0085).
    # It matters because the Preloading:/Retrieving: cases used to hard-code "download",
    # and the COMMIT pass re-reads every cached package and prints `Preloading: …
    # [already in cache]` for each. Left hard-coded, the commit pass re-emits
    # download-phase markers after the download has finished — flipping the GUI back to
    # "Downloading" and, because `want` is a per-invocation local, resetting its byte
    # total to zero at the exact moment installing begins.
    local step="$1" phase="${2:-download}" line frac preloaded=0 seen=0 got=0 want=0
    # `|| [[ -n $line ]]` so a final line with no trailing newline is not swallowed.
    while IFS= read -r line || [[ -n "$line" ]]; do
        printf '%s\n' "$line"
        case "$line" in
            "Overall download size:"*|"Package download size:"*)
                # zypper's own figure for the whole transaction, printed before the
                # download starts. It is what lets the GUI show "19 MB of 86 MB" and a
                # rate — the two numbers that tell a slow download from a stalled one.
                # Both wordings are real: "Package download size" is what the
                # classic_rpmtrans backend prints, "Overall download size" the other.
                [[ "$line" =~ ^(Overall|Package)\ download\ size:\ *([0-9.]+)\ *([KMG]?i?B) ]] \
                    && want=$(to_bytes "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}") ;;
            Preloading:*)
                # The parallel prefetch, and the phase a big download actually spends its
                # time in — zypper gives it neither a counter nor a size, so all we can
                # pass on is the tally and the transaction total. The GUI measures the
                # bytes itself (zypper's package cache is world-readable), which is the
                # only way this phase gets a figure at all.
                preloaded=$((preloaded+1)); seen=$((seen+1))
                marker PROGRESS "$step|$preloaded|0|$phase|0|$want" ;;
            Retrieving:*)
                frac=${line##*\(}; frac=${frac%%)*}      # last (…) is the counter
                # Each line ends with that package's size: "…(1/77),  31.0 KiB". Summing
                # them is the only byte count available — zypper reports no running total.
                [[ "$line" =~ ,\ *([0-9.]+)\ *([KMG]?i?B) ]] \
                    && got=$(( got + $(to_bytes "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}") ))
                emit_progress "$step" "$frac" "$phase" "$got" "$want" && seen=$((seen+1)) ;;
            \(*Installing:*|\(*Removing:*|\(*Upgrading:*)
                frac=${line#*\(}; frac=${frac%%)*}       # leading (…) is the counter
                emit_progress "$step" "$frac" install && seen=$((seen+1)) ;;
        esac
    done
    # The DOWNLOAD pass owns this file. The write truncates, so letting the commit pass
    # write too would erase the download pass's tally and trip the ONEUP-0046 stale-parser
    # canary ("packages installed but no progress recognised") on a perfectly healthy run.
    [[ -n "$PROGRESS_SEEN_FILE" && "$phase" == "download" ]] \
        && printf '%s' "$seen" > "$PROGRESS_SEEN_FILE"
    return 0        # our status is the pipeline's last, and a failed match must not
}                   # make the transaction itself look like it failed

# Pass 1 of 2. Downloads every package and installs NOTHING, so it is the one phase of a
# run that can be interrupted for free — and the stop the user asked for lands DURING it
# rather than after (ONEUP-0085). Sets `ok`; leaves rc 143 in SYS_DL_RC when the user
# stopped it, which §4.4 uses to tell "stopped" from "failed".
run_system_download() {
    ok=true
    system_txn_argv
    # The engine never signals anything: a root-side wrapper owns zypper and signals its
    # OWN child. Three measured facts force this shape — a background pipeline gets no
    # process group of its own (so a group kill would hit the engine, forbidden by §6.3),
    # `$!` names the pipeline's LAST element rather than zypper, and this shell is
    # unprivileged so it cannot signal a root process at all. Inside the wrapper all three
    # vanish. Keeping the pipeline in the FOREGROUND is what preserves PIPESTATUS[0].
    #
    # Two routes, one contract (ONEUP-0092 §4.5). When the ONEUP-0023 grant installed a
    # guard this engine recognises, run THAT — `env LC_ALL=C bash -c *` is the one shape a
    # sudoers rule cannot grant without handing over a root shell, so a passwordless run
    # would otherwise meet a password dialog right here. Otherwise run the inline wrapper
    # below, unchanged: users who never granted have a warm credential from sudo_init, so
    # it costs them nothing. The two texts differ (the guard pins its own interpreter and
    # zypper, and shifts 4 where this shifts 3) — never feed one into the other's call.
    if guard_current; then
        sudo "$GUARD_FILE" "$STOP_FILE" "$RUN_STATE_FILE" "$STOP_POLL_SECONDS" \
             "${SYS_TXN[@]}" 2>&1 | tee "$SYS_LOG" | progress_filter system download
        SYS_DL_RC=${PIPESTATUS[0]}
        (( SYS_DL_RC == 0 || SYS_DL_RC == 143 )) || ok=false
        return 0
    fi
    sudo env LC_ALL=C bash -c '
        stop_file="$1"; run_state="$2"; poll="$3"; shift 3
        "$@" --download-only &
        z=$!
        while kill -0 "$z" 2>/dev/null; do
            # Same staleness rule as stop_pending: a request older than run.state is a
            # leftover. Re-implemented because a shell function cannot cross sudo.
            if [[ -e "$stop_file" && -e "$run_state" && "$stop_file" -nt "$run_state" ]]; then
                kill -TERM "$z" 2>/dev/null
                break
            fi
            sleep "$poll"
        done
        wait "$z"        # never exit without reaping — an unreaped root child is the
        exit $?          # ONEUP-0041 orphan shape, one level down
    ' _ "$STOP_FILE" "$RUN_STATE_FILE" "$STOP_POLL_SECONDS" "${SYS_TXN[@]}" 2>&1 \
        | tee "$SYS_LOG" | progress_filter system download
    SYS_DL_RC=${PIPESTATUS[0]}
    # 143 is 128+SIGTERM: the user stopped it. Nothing is installed either way, so this is
    # not a failure — and it must not set ok=false, or the caller admits the step to the
    # repo-scoped-failure probe and re-runs the whole transaction the user just stopped.
    (( SYS_DL_RC == 0 || SYS_DL_RC == 143 )) || ok=false
}

# Pass 2 of 2. Every package is already cached, so this performs no network I/O — it is
# the rpm transaction and nothing else, which is exactly why it is NEVER signalled
# (security.md §6.1). Appends to $SYS_LOG: `tee` truncates, and the download pass's output
# is where a download failure's evidence lives.
run_system_commit() {
    ok=true
    system_txn_argv
    sudo env LC_ALL=C "${SYS_TXN[@]}" 2>&1 \
        | tee -a "$SYS_LOG" | progress_filter system install
    [[ ${PIPESTATUS[0]} -eq 0 ]] || ok=false
}

# Build a copy of REPOS_DIR whose openSUSE baseurls point at the content CDN, and echo its
# path. Empty output means there was nothing to redirect, or the copy failed — either way
# the caller reports the original failure (ONEUP-0094 §4.5).
#
# Only `baseurl=` lines are rewritten, and the `I` flags are the case-insensitivity the
# probe above assumes. Rewriting the whole file would also rename the [alias] header, and
# libzypp keys /var/cache/zypp/packages by ALIAS — so a renamed repository throws away
# every package already downloaded, which is exactly what ONEUP-0087 exists to keep.
# metalink=/mirrorlist= are deliberately untouched: they ARE the mirror selection this is
# recovering from.
make_cdn_reposd() {
    local dir
    dir=$(mktemp -d) || return 0                      # 0700 by default; root only reads it
    cp "$REPOS_DIR"/*.repo "$dir"/ 2>/dev/null || { rm -rf "$dir"; return 0; }
    sed -i -E '/^baseurl[[:space:]]*=/I s#(https?://)download\.opensuse\.org#\1downloadcontentcdn.opensuse.org#I' \
        "$dir"/*.repo 2>/dev/null || { rm -rf "$dir"; return 0; }
    printf '%s' "$dir"
}

_run_system_upgrade_inner() {
    # Split into a download pass and a commit pass so a stop can land during the long,
    # network-bound half. The rpm transaction itself is as uninterruptible as it ever was.
    SYS_DL_RC=0
    run_system_download
    if ! $ok; then
        # ONEUP-0094: openSUSE's mirror routing can send one package to a host that will
        # not serve it, and one unfetchable file discards the whole transaction. Retry the
        # DOWNLOAD pass once against the content CDN, which answers directly instead of
        # selecting a mirror that may not have the file yet. Runs BEFORE the caller's
        # repo-scoped probe: that probe's remedy is to disable a repository, and a transfer
        # failure is the one case where doing so throws away a working source.
        if ! $DL_RECOVERY_TRIED && ! stop_pending \
           && grep -qiE 'bytes missing|returned error: 404|Download.*failed|Curl error|connection failed' "$SYS_LOG" \
           && ! grep -qiE 'No space left|disk full|conflict|nothing provides|not installable|signature|GPG' "$SYS_LOG" \
           && grep -qiE '^baseurl[[:space:]]*=[[:space:]]*https?://download\.opensuse\.org' \
                        "$REPOS_DIR"/*.repo 2>/dev/null
        then
            # Command substitution is safe here only because make_cdn_reposd runs NOTHING
            # privileged — a sudo inside a subshell re-authenticates (security.md §2.2).
            local cdn_dir
            cdn_dir=$(make_cdn_reposd)
            if [[ -n "$cdn_dir" ]]; then
                CDN_REPOSD_DIR="$cdn_dir"     # cleanup handle; outlives REPOSD_OVERRIDE
                DL_RECOVERY_TRIED=true
                SYS_LOG_FIRST=$(mktemp)   # the retry's `tee` truncates SYS_LOG
                cp "$SYS_LOG" "$SYS_LOG_FIRST" 2>/dev/null || true
                REPOSD_OVERRIDE="$cdn_dir"
                echo "  Recovery: retrying downloads via downloadcontentcdn.opensuse.org (repositories copied to $cdn_dir)"
                SYS_DL_RC=0
                run_system_download
                $ok || DL_RETRY_FAILED=true
            fi
        fi
        $ok || return 0                  # a real download failure — caller reports it
    fi
    if (( SYS_DL_RC == 143 )) || stop_pending; then
        SYS_STOPPED=true                 # the third safe boundary (ONEUP-0085 §4.2)
        return 0
    fi
    run_system_commit
}

# The wrapper exists for one reason: the inner function has three exits, and
# REPOSD_OVERRIDE must be cleared on all of them. The caller's repo-skip path can call this
# a third time after disabling a repository — and `disable_repo` edits the REAL directory,
# so an attempt still reading the redirected copy would not see the repository that was
# just disabled (ONEUP-0094 §4.1).
run_system_upgrade() {   # runs the transaction into $SYS_LOG (truncates it); sets global `ok`
    _run_system_upgrade_inner
    local rc=$?
    REPOSD_OVERRIDE=""
    return $rc
}

echo
echo "########################################################"
echo "#            Starting System Update                    #"
echo "#   Steps: $STEPS"
echo "#   Log:   $LOG_FILE"
echo "########################################################"

# ---------------------------------------------------------------------------
# Step: system packages (Leap = update, Tumbleweed = dup)
# ---------------------------------------------------------------------------
if step_selected system && ! stop_pending; then
    begin_step system
    # Interactive "Skip & update the rest" re-run: set the named sources aside up front.
    for alias in "${SKIP_REPOS[@]:-}"; do
        [[ -z "$alias" ]] && continue
        disable_repo "$alias" manual || true
    done
    # The transaction below (dup/update) — NOT the refresh — decides whether the
    # step succeeded. A repo refresh can fail transiently (one mirror timing out)
    # while zypper still upgrades cleanly from cached metadata; failing the whole
    # step then would deny a working update and drop the reboot/service advice for
    # changes that really landed. So track refresh separately and, if it failed but
    # the upgrade succeeded, surface a non-fatal "used cached metadata" note.
    refresh_ok=true
    REFRESH_FAILED=false
    # One repository at a time, each with its own time budget, so a crawling mirror
    # can't hang the run and the GUI can name the source it's waiting on — see
    # refresh_repos, which also honours --import-keys (the user's approval to accept a
    # rotated signing key) and checks for a stop between repositories.
    refresh_repos
    if $REFRESH_FAILED; then refresh_ok=false; fi
    # Second safe boundary: the refresh above can take a minute on a slow mirror, so
    # honour a stop asked for during it. Nothing has been installed at this point, which
    # is exactly why stopping here is free — once the transaction starts it is seen
    # through, because interrupting rpm can leave programs broken.
    if stop_pending; then
        end_step system skip "stopped before installing anything"
    else
    # Capture the transaction output so we can tell whether anything actually
    # changed (for the summary and the reboot advice), while still streaming it.
    SYS_LOG=$(mktemp)
    PROGRESS_SEEN_FILE=$(mktemp)
    # Pin LC_ALL=C on the transaction whose output we parse below: the "Nothing to
    # do." / "N packages to upgrade" strings are translated on a non-English system,
    # and matching the English text keeps the change-detection reliable everywhere.
    # (`sudo env VAR=…` sets it in the child cleanly, regardless of sudoers env rules.)
    run_system_upgrade
    # Third safe boundary (ONEUP-0085): the user stopped during or just after the
    # download. Nothing was installed, so this is a skip — and it returns BEFORE the
    # repo-scoped-failure probe below, which would otherwise re-run the whole
    # transaction the user just stopped.
    if $SYS_STOPPED; then
        end_step system skip "stopped before installing anything"
        rm -f "$SYS_LOG" "$PROGRESS_SEEN_FILE" "$SYS_LOG_FIRST"
        [[ -n "$CDN_REPOSD_DIR" ]] && rm -rf "$CDN_REPOSD_DIR"   # rm -f cannot remove a dir
    else
    # Repo resilience: a repo-scoped failure (bad signature / unreachable / corrupt
    # metadata on ONE source) need not sink the whole run. Only probe when we
    # weren't already told which to skip (a --skip-repo run already named them —
    # probing again would be pointless and would mask a genuinely different error)
    # and the failure actually looks repo-scoped (disk-full/conflict are not).
    systemic_repo_fail=false
    if ! $ok && (( ${#SKIP_REPOS[@]} == 0 )) && repo_scoped_failure; then
        find_failing_repos                    # fills FAILING_REPOS[] in THIS shell
        failing=("${FAILING_REPOS[@]}")
        if (( ${#failing[@]} > MAX_SKIP_REPOS )); then
            systemic_repo_fail=true                       # too many at once → not one bad source
        elif (( ${#failing[@]} > 0 )); then
            if $AUTO_SKIP; then
                for entry in "${failing[@]}"; do
                    disable_repo "${entry%% *}" "${entry#* }" || true
                done
                # Retry on the healthy repos only if we actually managed to disable
                # something — a disable that itself failed must not silently retry.
                (( ${#DISABLED_REPOS[@]} > 0 )) && run_system_upgrade
            else
                # Interactive: ask, don't act. Offer "Skip <source> & update the
                # rest" for each culprit; disable nothing on our own.
                for entry in "${failing[@]}"; do marker REMEDY "skip-repo|${entry%% *}"; done
            fi
        fi
    fi
    # Only interpret the transaction output when the step actually SUCCEEDED. A
    # blocked/failed run has no "Nothing to do." line, so treating the else-branch
    # as "packages changed" would falsely trip the reboot advice — the step failed,
    # nothing was installed.
    if $ok; then
        if ! $refresh_ok; then
            # The upgrade worked, but off possibly-stale metadata — tell the user so
            # a genuinely-newer package isn't silently missed until the next run.
            note="Couldn't refresh one or more repositories — upgraded from cached metadata. A future run should refresh cleanly."
            echo "  Note: $note"
            marker HINT "$note"
        fi
        if grep -q "Nothing to do." "$SYS_LOG"; then
            SYS_COUNT=0
            end_step system ok "already up to date"
        else
            SYS_CHANGED=true
            # Canary for a stale parser. progress_filter reads zypper's own wording, so a
            # rename upstream makes progress silently stop — and silence is exactly how
            # the "download size: 0 B" bug hid for weeks (ONEUP-0035: zypper renamed
            # "Overall download size" to "Package download size" and OneUp believed the
            # wrong answer). A transaction that installed packages but produced no
            # progress at all is the signature of that, so say so rather than quietly
            # showing nothing (ONEUP-0046).
            if [[ "$(cat "$PROGRESS_SEEN_FILE" 2>/dev/null || echo 0)" == "0" ]]; then
                marker HINT "Packages were installed, but OneUp couldn't follow the progress — zypper has probably renamed the lines it reports progress on. The update itself was fine; please report this so the progress display can be updated."
                echo "  Note: no progress lines recognised in zypper's output (see @@HINT@@ above)."
            fi
            up=$(grep -oiE '[0-9]+ packages? to upgrade' "$SYS_LOG" | tail -1 | grep -oE '[0-9]+' | head -1)
            ins=$(grep -oiE '[0-9]+ to install' "$SYS_LOG" | tail -1 | grep -oE '[0-9]+' | head -1)
            SYS_COUNT=$(( ${up:-0} + ${ins:-0} ))
            # Read the reboot-reason names now, while the transaction log still exists
            # (it is rm'd at the end of this step, long before the reboot check below).
            SYS_REBOOT_DETAIL=$(reboot_reason_from_log "$SYS_LOG")
            if (( SYS_COUNT > 0 )); then
                end_step system ok "$SYS_COUNT package(s) updated"
            else
                end_step system ok "packages updated"
            fi
        fi
        if (( ${#DISABLED_REPOS[@]} > 0 )); then
            note="Updated everything except: ${DISABLED_REPOS[*]} — set aside this run (temporary problem); OneUp will retry next time."
            echo "  Note: $note"
            marker HINT "$note"
        fi
        # ONEUP-0094: the update only completed because the download was retried against
        # the CDN. Say so — this hint reports a run that already succeeded, so unlike the
        # failure hints it has nothing for the user to do.
        if $DL_RECOVERY_TRIED && ! $DL_RETRY_FAILED; then
            note="Recovered from a failed download — some packages were fetched from openSUSE's content delivery network instead of the mirror that failed."
            echo "  Note: $note"
            marker HINT "$note"
        fi
    else
        # Turn the most common zypper failures into one plain-English line.
        hint=""
        if $systemic_repo_fail; then
            hint="Several repositories are failing at once — likely a network or system problem, not a single bad source. Check your connection and retry."
        elif $DL_RETRY_FAILED \
             && grep -qiE 'bytes missing|returned error: 404|Download.*failed|Curl error|connection failed' "$SYS_LOG"; then
            # ONEUP-0094: recovery ran and the download still failed. Guarded on
            # DL_RETRY_FAILED rather than DL_RECOVERY_TRIED — the latter is still true when
            # the retry SUCCEEDED and the commit then failed, where "nothing was installed"
            # would be a lie. The log is re-tested so a retry that died of a full disk still
            # reaches the disk-full arm below.
            #
            # Name the package from the FIRST attempt's snapshot: the retry's `tee`
            # truncated SYS_LOG. A bracketed clause that is neither "done" nor "already in
            # cache" is the failure; anything else and we drop the clause rather than
            # print an empty one.
            failed_pkg=$(grep -oE '^(Preloading|Retrieving): [^ ]+ \[[^]]*\]' "$SYS_LOG_FIRST" 2>/dev/null \
                         | grep -viE '\[(done|already in cache)\]' \
                         | head -1 | awk '{print $2}')
            if [[ -n "$failed_pkg" ]]; then
                hint="Could not download $failed_pkg — openSUSE's servers are still catching up with this update. Nothing was installed and everything already downloaded has been kept; try again later."
            else
                hint="A package could not be downloaded — openSUSE's servers are still catching up with this update. Nothing was installed and everything already downloaded has been kept; try again later."
            fi
        elif grep -qiE 'No space left|disk full' "$SYS_LOG"; then
            hint="Ran out of disk space — free some room (clear the package cache, delete old snapshots) and retry."
        elif grep -qiE 'signature|GPG|key.*(expired|reject)' "$SYS_LOG"; then
            if $IMPORT_KEYS; then
                # We already imported keys this run and it STILL failed — importing
                # won't help, so don't offer the one-click remedy again.
                hint="A repository signing key is still rejected even after importing keys — check the log for the offending repository, or run: sudo zypper --gpg-auto-import-keys refresh, then retry."
            else
                # A one-click fix exists: tell the GUI to offer "Import signing key &
                # retry" (which re-runs with --import-keys after a warned confirmation).
                marker REMEDY "import-keys"
                hint="A repository signing key is out of date. Use \"Import signing key & retry\" to fix it, or run: sudo zypper --gpg-auto-import-keys refresh, then retry."
            fi
        elif grep -qiE 'Timeout|could not resolve|connection failed|Curl error|Download.*failed|Temporary failure' "$SYS_LOG"; then
            hint="A download failed — check your internet connection, then retry."
        elif grep -qiE 'conflict|nothing provides|not installable' "$SYS_LOG"; then
            hint="A package conflict — often a third-party repo. Check the log; you may need to disable a conflicting repository."
        fi
        if [[ -n "$hint" ]]; then
            echo "  Hint: $hint"
            marker HINT "$hint"
        fi
        end_step system fail "zypper reported an error"
    fi
    rm -f "$SYS_LOG" "$PROGRESS_SEEN_FILE" "$SYS_LOG_FIRST"
    [[ -n "$CDN_REPOSD_DIR" ]] && rm -rf "$CDN_REPOSD_DIR"   # rm -f cannot remove a dir
    fi      # closes the SYS_STOPPED guard (ONEUP-0085's third safe boundary)
    fi      # closes the stop_pending guard above the transaction
fi

# ---------------------------------------------------------------------------
# Step: Flatpak (user scope needs no root; system scope reuses cached sudo)
# ---------------------------------------------------------------------------
if step_selected flatpak && ! stop_pending; then
    begin_step flatpak
    if command -v flatpak &>/dev/null; then
        ok=true
        # Count what will update first (same read-only check --check uses), so the
        # summary and GUI can report how many apps were updated, not just "done".
        flat_count=$(( $(flatpak remote-ls --updates --user 2>/dev/null | wc -l) \
                     + $(flatpak remote-ls --updates --system 2>/dev/null | wc -l) ))
        flatpak update --user -y || ok=false
        sudo flatpak update --system -y || ok=false
        echo "Cleaning up unused Flatpak runtimes..."
        flatpak uninstall --user --unused -y || true
        sudo flatpak uninstall --system --unused -y || true
        if $ok; then
            if (( flat_count > 0 )); then
                end_step flatpak ok "$flat_count app(s) updated"
            else
                end_step flatpak ok "up to date"
            fi
        else
            end_step flatpak fail "a flatpak update failed"
        fi
    else
        echo "Flatpak is not installed. Skipping."
        end_step flatpak skip "not installed"
    fi
fi

# ---------------------------------------------------------------------------
# Step: firmware (fwupd elevates via polkit on its own)
# ---------------------------------------------------------------------------
if step_selected firmware && ! stop_pending; then
    begin_step firmware
    if command -v fwupdmgr &>/dev/null; then
        fwupdmgr refresh || true
        if fwupdmgr get-updates &>/dev/null; then
            # Only claim success (and later advise a reboot) if the flash actually
            # succeeded — a failed update must not report "applied" or force a reboot.
            if fwupdmgr update -y; then
                FW_CHANGED=true
                end_step firmware ok "updates applied"
            else
                end_step firmware fail "firmware update failed"
            fi
        else
            echo "No firmware updates available."
            end_step firmware ok "up to date"
        fi
    else
        echo "fwupd is not installed. Skipping."
        end_step firmware skip "not installed"
    fi
fi

# ---------------------------------------------------------------------------
# Step: remove leftover packages (SAFE autoremove).
#   * Removes only "unneeded" packages — installed as dependencies and no longer
#     required by anything. Every removed package is logged.
#   * "Orphaned" packages (installed but provided by no active repo) are only
#     REPORTED, never auto-removed: they are often software you installed by hand.
#   * The pre-update snapshot makes even the autoremove reversible.
# ---------------------------------------------------------------------------
if step_selected orphans && ! stop_pending; then
    begin_step orphans
    # zypper auto-refreshes any stale repository before it will answer a `packages`
    # query, so with the system step deselected that fetch happens inside the
    # sudo_capture below — where it loses both of ONEUP-0048's defences at once. Its
    # output goes into a variable instead of the log pane, and it runs outside
    # refresh_repos' per-source budget, so a crawling mirror hangs the whole run with
    # the window showing nothing at all. Measured 2026-08-03 on --steps=flatpak,orphans,
    # cache: 81 s on one source, silent, and the GUI's stall warning fired on a run that
    # was working perfectly. Refresh here under the guard instead, then forbid the
    # implicit one below — the same metadata, now named, bounded and stoppable.
    $REPOS_REFRESHED || refresh_repos
    if stop_pending; then
        # refresh_repos returns between sources when a stop is asked for, and nothing has
        # been removed yet — the same free boundary the system step stops at.
        end_step orphans skip "stopped before removing anything"
    else
    # --no-refresh on both queries: the refresh above is the only one allowed to happen,
    # because it is the only one the user can see and the run can escape from.
    sudo_capture UNNEEDED_RAW zypper --non-interactive --no-refresh packages --unneeded
    mapfile -t UNNEEDED < <(awk -F'|' \
        'NR>2 && $3 !~ /^[[:space:]]*$/ {gsub(/ /,"",$3); print $3}' <<<"$UNNEEDED_RAW")
    if ((${#UNNEEDED[@]})); then
        echo "Removing ${#UNNEEDED[@]} leftover dependency package(s):"
        printf '  - %s\n' "${UNNEEDED[@]}"
        if sudo zypper --non-interactive remove --clean-deps "${UNNEEDED[@]}"; then
            end_step orphans ok "removed ${#UNNEEDED[@]} package(s)"
        else
            end_step orphans fail "removal failed"
        fi
    else
        echo "No leftover dependency packages to remove."
        end_step orphans ok "nothing to remove"
    fi
    # Report-only: packages with no active repo (do NOT auto-remove these).
    sudo_capture ORPHAN_RAW zypper --non-interactive --no-refresh packages --orphaned
    ORPHAN_COUNT=$(awk -F'|' 'NR>2 && $3 !~ /^[[:space:]]*$/' <<<"$ORPHAN_RAW" | wc -l)
    if ((ORPHAN_COUNT > 0)); then
        echo
        echo "Note: $ORPHAN_COUNT package(s) have no active repository (possibly"
        echo "installed by hand). Left in place — review with:  zypper packages --orphaned"
    fi
    fi
fi

# ---------------------------------------------------------------------------
# Step: clean the zypper package cache
# ---------------------------------------------------------------------------
if step_selected cache && ! stop_pending; then
    begin_step cache
    # A system step that failed almost always failed PART-WAY THROUGH THE DOWNLOAD,
    # which means the cache now holds most of what the retry needs. Clearing it turns
    # one flaky mirror into a full re-download. Measured 2026-08-07: kernel-default
    # aborted with 194 MB missing, the step failed, and this step then reclaimed
    # 424 MB — so the retry started again from zero, over the same mirror that had
    # just dropped the connection (ONEUP-0087). Disk space is worth far less than a
    # download that finally completes.
    if [[ "${RESULT[system]:-}" == "fail" ]]; then
        note="Kept the already-downloaded packages, so retrying the update doesn't fetch them all over again."
        echo "  $note"
        marker HINT "$note"
        end_step cache skip "kept the downloads for a retry"
    else
    # Measure the package cache before/after the clean so we can report what it
    # freed — the cache step is otherwise the one task with no visible payoff.
    # du needs root for some subdirs; this step's sudo credential is already warm.
    # One definition, shared with the sudoers rule that grants it (ONEUP-0092).
    sudo_capture CACHE_DU "${CACHE_DU_ARGV[@]}"
    cache_before=$(awk '{print $1}' <<<"$CACHE_DU")
    # Packages only — deliberately NOT `clean --all`, which also wipes the repository
    # METADATA cache. Two reasons, and the first is a correctness bug: the rootless
    # `--check` reads that metadata and cannot rebuild it, so wiping it made the very
    # next check answer "up to date" no matter what was actually waiting (ONEUP-0056).
    # Second, metadata is not the win it looks like — 93 MB here, every byte of which
    # zypper re-downloads on the next run. This step's own label promises "the
    # downloaded-package cache"; now it clears exactly that.
    if sudo zypper --non-interactive clean; then
        end_step cache ok
        sudo_capture CACHE_DU "${CACHE_DU_ARGV[@]}"
        cache_after=$(awk '{print $1}' <<<"$CACHE_DU")
        # Only report a genuine reclamation — skip the marker when nothing shrank
        # so the GUI never shows a misleading "Reclaimed 0B".
        if [[ "$cache_before" =~ ^[0-9]+$ && "$cache_after" =~ ^[0-9]+$ ]] \
           && (( cache_before > cache_after )); then
            freed=$(numfmt --to=iec $(( cache_before - cache_after )) 2>/dev/null \
                    || echo "$(( cache_before - cache_after ))B")
            echo "  Reclaimed $freed from the package cache."
            marker FREED "cache|$freed"
        fi
    else
        end_step cache fail "clean failed"
    fi
    fi      # closes the "system step failed — keep the downloads" guard above
fi

# ---------------------------------------------------------------------------
# Reboot check
# ---------------------------------------------------------------------------
REBOOT="no"
REBOOT_REASON=""
if command -v zypper &>/dev/null; then
    # Read-only check; runs without root. zypper exits EXACTLY 102 when a reboot
    # is advised (core libraries or the kernel changed), 0 when it is not. Any
    # OTHER non-zero code means the check itself failed (e.g. the lock was held) —
    # we must NOT read that as "reboot needed", or a blocked run nags forever.
    zypper needs-rebooting &>/dev/null
    if [[ $? -eq 102 ]]; then
        REBOOT="yes"
        # Prefer the specific "a new kernel / your NVIDIA driver … was installed"
        # phrase gathered from this run's transaction log; fall back to a generic
        # reason when the reboot is owed to core libraries we didn't name.
        REBOOT_REASON="${SYS_REBOOT_DETAIL:-core system packages were updated}"
    fi
fi
if [[ "$REBOOT" == "no" ]] && $FW_CHANGED; then
    # Firmware changes generally need a reboot to take effect.
    REBOOT="yes"
    REBOOT_REASON="firmware was updated"
fi
# Package-only changes (no kernel/core-lib bump, no firmware) do NOT force a
# reboot — the service-restart step below offers the lighter alternative.
marker INSTALLED "${SYS_COUNT}|$($SYS_CHANGED && echo yes || echo no)|$($FW_CHANGED && echo yes || echo no)"
# Append the reason only when a reboot is advised, so the no-reboot marker stays
# exactly "@@REBOOT@@|no" (the GUI and tests read the reason as an optional field).
marker REBOOT "$REBOOT${REBOOT_REASON:+|$REBOOT_REASON}"

# ---------------------------------------------------------------------------
# Services running against replaced libraries. `zypper ps -sss` prints just the
# affected systemd service names. When a full reboot is NOT required, restarting
# these lets the user pick up the new libraries without rebooting.
# ---------------------------------------------------------------------------
SERVICES=""
if $SYS_CHANGED && [[ "$REBOOT" == "no" ]] && command -v zypper &>/dev/null; then
    sudo_capture SERVICES_RAW zypper ps -sss
    SERVICES=$(tr '\n' ' ' <<<"$SERVICES_RAW" | sed 's/[[:space:]]*$//')
    [[ -n "$SERVICES" ]] && marker SERVICES "$SERVICES"

    # Split the list for the printed advice below (ONEUP-0111). Restarting one of these
    # ends the user's graphical session, so a reboot is the honest advice; the marker
    # above is deliberately UNCHANGED and still carries every name, because the window
    # does its own split and `docs/reference/marker-protocol.md` §5.1 freezes the field
    # during 2.0. Kept in step with updater.py's _SESSION_CRITICAL by a test.
    SERVICES_SAFE=""; SERVICES_RISKY=""
    dm_unit=$(readlink -f /etc/systemd/system/display-manager.service 2>/dev/null || true)
    dm_unit=${dm_unit##*/}; dm_unit=${dm_unit%.service}
    for svc in $SERVICES; do
        base=${svc%.service}
        if [[ "$base" =~ ^(display-manager|sddm|gdm|gdm3|lightdm|xdm|kdm|lxdm|greetd|dbus|dbus-broker|systemd-logind|polkit|polkitd|user@[0-9]+)$ ]] \
           || { [[ -n "$dm_unit" ]] && [[ "$base" == "$dm_unit" ]]; }; then
            SERVICES_RISKY+="${SERVICES_RISKY:+ }$svc"
        else
            SERVICES_SAFE+="${SERVICES_SAFE:+ }$svc"
        fi
    done
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "=========================================="
echo "               Summary                    "
echo "=========================================="
for key in "${RUN_KEYS[@]}"; do
    status="${RESULT[$key]:-skip}"
    detail="${DETAIL[$key]:-}"
    secs="${SECS[$key]:-0}"
    case "$status" in
        ok)   icon="OK  " ;;
        skip) icon="SKIP" ;;
        fail) icon="FAIL" ;;
        *)    icon="?   " ;;
    esac
    printf '  [%s] %-26s %3ds%s\n' "$icon" "${LABEL[$key]}" "$secs" \
        "${detail:+   ($detail)}"
done
echo "------------------------------------------"
# Whether anything was actually installed (drives the reboot advice).
if step_selected system; then
    if [[ "$SYS_COUNT" == "0" ]]; then
        echo "  Updates installed: none — system was already up to date."
    elif [[ -n "$SYS_COUNT" && "$SYS_COUNT" != "0" ]]; then
        echo "  Updates installed: $SYS_COUNT system package(s)."
    elif $SYS_CHANGED; then
        echo "  Updates installed: yes (system packages updated)."
    fi
fi
$FW_CHANGED && echo "  Firmware: updates applied."
echo "------------------------------------------"
if ((ERRORS > 0)); then
    echo "  Finished with $ERRORS error(s) — see the log above."
    marker DONE "errors"
elif $STOP_HONOURED; then
    # Not "ok": the run did not do what was asked of it. Not "errors" either — nothing
    # went wrong. The GUI reports it as stopped, so neither claim is made.
    echo "  Stopped at your request — the steps above are all that ran."
    marker DONE "stopped"
else
    echo "  All selected steps completed cleanly."
    marker DONE "ok"
fi
if [[ "$REBOOT" == "yes" ]]; then
    echo
    echo "  ! A REBOOT is recommended — $REBOOT_REASON."
elif [[ -n "$SERVICES" ]]; then
    if [[ -n "$SERVICES_SAFE" ]]; then
        echo
        echo "  ! No reboot needed for these services, but they should restart to use the"
        echo "    new libraries:  $SERVICES_SAFE"
    fi
    # ONEUP-0115: where the honest answer is a reboot, SAY so in the same words the
    # reboot path uses, rather than naming units under a heading that has just said no
    # reboot is needed. `zypper needs-rebooting` did not ask for one, so this stays a
    # recommendation in the printed advice and the @@REBOOT@@ marker is untouched —
    # docs/reference/marker-protocol.md §5.1 freezes the contract during 2.0.
    if [[ -n "$SERVICES_RISKY" ]]; then
        echo
        echo "  ! A REBOOT is recommended — these hold replaced libraries, and restarting"
        echo "    them would BREAK OR END your desktop session:"
        echo "      $SERVICES_RISKY"
    fi
fi

# End-of-run desktop notification (full runs only; --check has its own at line ~229).
# Fires for the unattended weekly timer so a 2am run still reports its outcome.
if $NOTIFY; then
    # Unattended auto-skip sets a source aside silently — the notification is the
    # ONLY place a nobody's-watching run reports what it skipped, so name it here.
    skip_note=""
    (( ${#DISABLED_REPOS[@]} > 0 )) && skip_note=" (skipped: ${DISABLED_REPOS[*]} — will retry next time)"
    if ((ERRORS > 0)); then
        notify_send "Update failed" "One or more steps failed — see the log: $LOG_FILE"
    elif [[ -n "$SYS_COUNT" && "$SYS_COUNT" != "0" ]]; then
        notify_send "Update complete" "$SYS_COUNT system package(s) installed.$skip_note"
    elif $SYS_CHANGED || $FW_CHANGED; then
        notify_send "Update complete" "Updates were installed.$skip_note"
    else
        notify_send "Already up to date" "No updates were needed.$skip_note"
    fi
fi
echo "  Log saved: $LOG_FILE"
echo "=========================================="

# Non-zero exit if anything failed, so the GUI can colour the run accordingly.
((ERRORS == 0))
