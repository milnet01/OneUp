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

ASKPASS=/usr/libexec/ssh/ksshaskpass

# ---------------------------------------------------------------------------
# Configuration / arguments
# ---------------------------------------------------------------------------
ALL_STEPS="system,flatpak,firmware,orphans,cache"
STEPS="$ALL_STEPS"
LOG_DIR="$HOME/Documents/update-logs"
LOG_FILE=""
CHECK_ONLY=false   # --check: report what WOULD update, install nothing, no root
NOTIFY=false       # --notify: fire a desktop notification if updates are found
SIZE_STEP=""       # --size=<step>: on-demand exact download size (needs root)
AUTH_ACTION=""     # --grant-auth / --revoke-auth / --auth-status: manage the
                   # opt-in "remember my authorization" sudoers drop-in.
IMPORT_KEYS=false  # --import-keys: refresh with --gpg-auto-import-keys so a rotated
                   # or expired repo signing key is imported for the system upgrade.
                   # Opt-in per run (the GUI sets it only after a warned confirmation).
SKIP_REPOS=()      # --skip-repo=<alias> (repeatable): sources to set aside this run
AUTO_SKIP=false    # --auto-skip-repos: unattended auto-quarantine of a broken source
DISABLED_REPOS=()  # aliases WE disabled this run; cleanup() re-enables every one
MAX_SKIP_REPOS=2   # more than this failing at once = systemic, don't silently skip

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
        --grant-auth)  AUTH_ACTION="grant" ;;
        --revoke-auth) AUTH_ACTION="revoke" ;;
        --auth-status) AUTH_ACTION="status" ;;
        --import-keys) IMPORT_KEYS=true ;;
        --skip-repo=*)     SKIP_REPOS+=("${arg#*=}") ;;
        --auto-skip-repos) AUTO_SKIP=true ;;
        --notify)  NOTIFY=true ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

step_selected() { [[ ",$STEPS," == *",$1,"* ]]; }

# ---------------------------------------------------------------------------
# Logging: mirror everything to the log file as well as the console/GUI.
# ---------------------------------------------------------------------------
mkdir -p "$LOG_DIR"
if [[ -z "$LOG_FILE" ]]; then
    LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d_%H%M).log"
fi
exec > >(tee -a "$LOG_FILE") 2>&1

# ---------------------------------------------------------------------------
# Progress-marker helpers (consumed by the GUI; benign in a terminal).
#   @@STEP_BEGIN@@|key|index|total|Human label
#   @@STEP_END@@|key|ok|skip|fail|detail
#   @@TIMING@@|key|seconds               (how long the step took)
#   @@SNAPSHOT@@|id
#   @@CHECK@@|key|count|label            (--check mode: updates available)
#   @@CHECK_ITEM@@|key|name|from|to      (--check mode: one changed package)
#   @@SIZE@@|key|download                (--size mode: total download size)
#   @@FREED@@|key|human                  (disk reclaimed by the cache clean)
#   @@AUTH@@|on|off                      (passwordless-authorization state)
#   @@DISK@@|warn|mount|free             (pre-flight: low disk space)
#   @@REPO@@|warn|reason                 (pre-flight: repo health issue)
#   @@HINT@@|plain-English failure hint
#   @@REMEDY@@|import-keys               (a one-click GUI fix is available for this failure)
#   @@REPO_SKIPPED@@|alias|reason        (a source was set aside this run)
#   @@REMEDY@@|skip-repo|alias           (offer "Skip <source> & update the rest")
#   @@SERVICES@@|svc1 svc2 …             (services to restart instead of rebooting)
#   @@INSTALLED@@|count|sys_changed|fw_changed   (yes/no flags for the summary)
#   @@REBOOT@@|yes|no
#   @@DONE@@|ok|errors
# ---------------------------------------------------------------------------
marker() { printf '@@%s@@|%s\n' "$1" "$2"; }

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
FW_CHANGED=false    # did firmware updates get applied?

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

# ---------------------------------------------------------------------------
# --check: read-only "what would update?" pass. Deliberately avoids root (and a
# password popup) so an unattended timer can run it; it reads cached repo
# metadata, which the system keeps reasonably fresh, and installs nothing.
# ---------------------------------------------------------------------------
run_check() {
    echo "Checking for available updates (read-only)…"
    local total=0 n
    if step_selected system; then
        # Read the upgrade list once: the count AND the per-package detail (name,
        # current → available version) the GUI shows in its expandable preview both
        # come from it. LC_ALL=C keeps the column layout parseable on any locale.
        local updates
        updates=$(LC_ALL=C zypper --no-refresh --non-interactive list-updates 2>/dev/null)
        # Upgradable packages have a 'v' in zypper's status column.
        n=$(grep -cE '^v[[:space:]]*\|' <<<"$updates")
        marker CHECK "system|$n|system package(s)"
        # Columns: S | Repository | Name | Current | Available | Arch. Trim each
        # field and emit one CHECK_ITEM per package (one awk pass, no per-line fork).
        while IFS='|' read -r name cur avail; do
            [[ -n "$name" ]] && marker CHECK_ITEM "system|$name|$cur|$avail"
        done < <(awk -F'|' '/^v[[:space:]]*\|/ {
                    for (i=3;i<=5;i++) gsub(/^[ \t]+|[ \t]+$/,"",$i); print $3"|"$4"|"$5 }' \
                 <<<"$updates")
        echo "  System packages: $n update(s)"
        (( total += n ))
    fi
    if step_selected flatpak && command -v flatpak &>/dev/null; then
        # --columns pins the output to app-id + version so both the count and the
        # per-app detail parse the same way regardless of flatpak's default columns.
        local flatpaks
        flatpaks=$(
            flatpak remote-ls --updates --user --columns=application,version 2>/dev/null
            flatpak remote-ls --updates --system --columns=application,version 2>/dev/null
        )
        n=$(grep -c '[^[:space:]]' <<<"$flatpaks")
        marker CHECK "flatpak|$n|Flatpak app(s)"
        while read -r app ver _rest; do
            [[ -n "$app" ]] && marker CHECK_ITEM "flatpak|$app||$ver"
        done <<<"$flatpaks"
        echo "  Flatpak apps: $n update(s)"
        (( total += n ))
    fi
    if step_selected firmware && command -v fwupdmgr &>/dev/null; then
        if fwupdmgr get-updates &>/dev/null; then n=1; else n=0; fi
        marker CHECK "firmware|$n|firmware update(s)"
        echo "  Firmware: $( ((n > 0)) && echo available || echo up to date)"
        (( total += n ))
    fi
    marker CHECK "TOTAL|$total|updates available"
    echo "  Total: $total update(s) available."
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
run_size() {
    local step="$1" out size
    if [[ "$step" != "system" ]]; then
        echo "Download-size preview is only available for the system step." >&2
        return 2
    fi
    sudo_init
    release_zypper_lock
    echo "Calculating download size (dry run)…"
    if [[ -f /etc/os-release ]] && grep -q "Leap" /etc/os-release; then
        out=$(sudo env LC_ALL=C zypper --non-interactive update --dry-run 2>&1)
    else
        out=$(sudo env LC_ALL=C zypper --non-interactive dup --allow-vendor-change --dry-run 2>&1)
    fi
    # zypper prints e.g. "Overall download size: 1.3 GiB. Already cached: 0 B."
    # Capture the number+unit (LC_ALL=C above pins '.' as the decimal point, so the
    # value can't run into the trailing sentence).
    size=$(sed -n 's/.*Overall download size: \([0-9.]\+ [A-Za-z]\+\).*/\1/p' \
        <<<"$out" | head -n1)
    if [[ -n "$size" ]]; then
        marker SIZE "system|$size"
        echo "  Download size: $size"
        marker DONE "ok"
    else
        # No size line = nothing to fetch (up to date / all cached). Report zero so
        # the GUI shows a definitive answer rather than treating it as a failure.
        marker SIZE "system|0 B"
        echo "  Download size: nothing to fetch."
        marker DONE "ok"
    fi
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
    # If the ONEUP-0023 passwordless drop-in is active, every privileged command
    # below is individually NOPASSWD, so no cached credential is needed — and the
    # interactive `sudo -A … -v` here would prompt ANYWAY: sudo's `verifypw` defaults
    # to `all`, so a bare `-v` validate is only password-free when EVERY one of the
    # user's sudoers entries is NOPASSWD (a normal %wheel user's isn't). Skipping it
    # is what lets a headless timer run authenticate. Same non-interactive scoped
    # probe --auth-status uses (auth_status, ~line 416).
    local _zypper
    if _zypper=$(command -v zypper) && sudo -k -n "$_zypper" --version >/dev/null 2>&1; then
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
    setsid bash -c 'while true; do sudo -n -v 2>/dev/null || true; sleep 50; done' \
        >/dev/null 2>&1 &
    SUDO_KEEPALIVE=$!
}
# Negative PID targets the keep-alive's process group (the loop shell + its sleep),
# so nothing survives the run. See sudo_init for why setsid makes this a lone group.
# Re-enable every repo we disabled BEFORE killing the keep-alive (sudo cred still
# warm), non-interactively (-n) so a cold-credential exit logs the manual fix
# instead of blocking on a ksshaskpass popup inside the trap.
cleanup() {
    local a
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

# Build the drop-in text from the binaries actually present on THIS machine
# (command -v, not a hardcoded /usr/bin) so each rule matches the exact path sudo
# will resolve. zypper is required; the rest are optional (skipped if absent).
build_auth_rule() {
    local user zypper cmd cmds=()
    user=$(id -un)
    zypper=$(command -v zypper) || return 1
    cmds+=("$zypper")                                   # any zypper subcommand
    cmd=$(command -v snapper)   && cmds+=("$cmd")        # snapper create/list
    cmd=$(command -v flatpak)   && cmds+=("$cmd")        # flatpak update/uninstall
    cmd=$(command -v systemctl) && cmds+=("$cmd stop packagekit")
    # The engine pins the locale via `sudo env LC_ALL=C zypper …`. sudo resolves the
    # command (env) to a path but matches the REST of the argv literally, so this
    # pattern's second word must be the bare `zypper` the engine typed, not its path.
    cmd=$(command -v env)       && cmds+=("$cmd LC_ALL=C zypper *")
    local joined
    printf -v joined '%s, ' "${cmds[@]}"
    cat <<EOF
# Installed by OneUp's "remember my authorization" setting — stores NO password.
# Lets $user run OneUp's update commands as root without a password prompt.
# Delete this file (or turn the setting off in OneUp) to revoke immediately.
Cmnd_Alias ONEUP_UPDATE = ${joined%, }
$user ALL=(root) NOPASSWD: ONEUP_UPDATE
EOF
}

grant_auth() {
    local tmp
    tmp=$(mktemp) || { marker HINT "Could not create a temporary file."; return 1; }
    if ! build_auth_rule > "$tmp"; then
        rm -f "$tmp"
        marker HINT "zypper was not found, so passwordless authorization can't be set up."
        return 1
    fi
    sudo_init
    # Validate the generated rule in isolation BEFORE it can affect the live policy:
    # a syntactically broken file under /etc/sudoers.d can lock you out of sudo.
    if ! sudo visudo -cf "$tmp" >/dev/null 2>&1; then
        rm -f "$tmp"
        marker HINT "The generated authorization rule failed validation — nothing was changed."
        return 1
    fi
    # install(1) atomically places it root-owned and 0440, the mode sudo requires.
    if ! sudo install -o root -g root -m 0440 "$tmp" "$AUTH_FILE"; then
        rm -f "$tmp"
        marker HINT "Could not write the authorization rule ($AUTH_FILE)."
        return 1
    fi
    rm -f "$tmp"
    echo "Passwordless authorization for OneUp's update commands is now enabled."
    marker AUTH "on"
}

revoke_auth() {
    sudo_init
    if sudo rm -f "$AUTH_FILE"; then
        echo "Passwordless authorization has been revoked."
        marker AUTH "off"
    else
        marker HINT "Could not remove the authorization rule ($AUTH_FILE)."
        return 1
    fi
}

auth_status() {
    local zypper
    zypper=$(command -v zypper) || { marker AUTH "off"; return 0; }
    # `-k` ignores any cached credential (so a recent run can't false-positive) and
    # `-n` refuses to prompt, so this harmless `zypper --version` runs as root ONLY
    # when the NOPASSWD drop-in is active. No root file-read needed (it's root-only).
    if sudo -k -n "$zypper" --version >/dev/null 2>&1; then
        marker AUTH "on"
    else
        marker AUTH "off"
    fi
}

if [[ -n "$AUTH_ACTION" ]]; then
    case "$AUTH_ACTION" in
        grant)  grant_auth ;;
        revoke) revoke_auth ;;
        status) auth_status ;;
    esac
    exit $?
fi

# --size=<step>: report the download size and exit, never falling through into a
# real update. Placed here so run_size can reuse sudo_init/release_zypper_lock,
# both of which are now defined.
if [[ -n "$SIZE_STEP" ]]; then
    run_size "$SIZE_STEP"
    exit $?
fi

# Firmware uses polkit for its own elevation; every other root step reuses the
# cached sudo credential, so we only bootstrap when a sudo step is selected.
needs_sudo=false
for k in system flatpak orphans cache; do
    step_selected "$k" && needs_sudo=true
done
$needs_sudo && sudo_init

# With the credential warm, make sure PackageKit isn't sitting on the lock.
$needs_sudo && release_zypper_lock

# ---------------------------------------------------------------------------
# Pre-update snapshot note (btrfs/snapper rollback point). Read-only: Tumbleweed
# already auto-snapshots around zypper; we just surface the latest id so the log
# records a rollback target.
# ---------------------------------------------------------------------------
if step_selected system && command -v snapper &>/dev/null; then
    # Create a clearly-labelled rollback point so the pre-update state is easy to
    # find later. (Tumbleweed also auto-snapshots around zypper, but a named entry
    # is unambiguous.) Fall back to reporting the newest snapshot if create fails.
    SNAP_ID=$(sudo snapper create --description "OneUp pre-update $(date '+%Y-%m-%d %H:%M')" \
        --cleanup-algorithm number --print-number 2>/dev/null)
    [[ -z "$SNAP_ID" ]] && SNAP_ID=$(sudo snapper --no-headers list 2>/dev/null | tail -n1 | awk '{print $1}')
    if [[ -n "$SNAP_ID" ]]; then
        echo "Pre-update snapshot #$SNAP_ID recorded  (roll back with: sudo snapper rollback $SNAP_ID)"
        marker SNAPSHOT "$SNAP_ID"
    fi
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

run_system_upgrade() {   # runs the transaction into $SYS_LOG (truncates it); sets global `ok`
    ok=true
    if [[ -f /etc/os-release ]] && grep -q "Leap" /etc/os-release; then
        sudo env LC_ALL=C zypper --non-interactive update 2>&1 | tee "$SYS_LOG"
    else
        # Tumbleweed: --allow-vendor-change lets Packman codec packages update
        # cleanly; without it the upgrade stalls on vendor conflicts.
        sudo env LC_ALL=C zypper --non-interactive dup --allow-vendor-change 2>&1 | tee "$SYS_LOG"
    fi
    [[ ${PIPESTATUS[0]} -eq 0 ]] || ok=false
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
if step_selected system; then
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
    if $IMPORT_KEYS; then
        # The user approved importing repository signing keys (via the GUI's
        # confirmation, or --import-keys on the CLI), so refresh WITH key import: a
        # rotated/expired key is accepted for the repos they've chosen to trust. This
        # is opt-in per run and never the default — a plain run stays strict and only
        # advises the fix (emitting @@REMEDY@@ below for the GUI's one-click button).
        sudo zypper --non-interactive --gpg-auto-import-keys refresh || refresh_ok=false
    else
        sudo zypper --non-interactive refresh || refresh_ok=false
    fi
    # Capture the transaction output so we can tell whether anything actually
    # changed (for the summary and the reboot advice), while still streaming it.
    SYS_LOG=$(mktemp)
    # Pin LC_ALL=C on the transaction whose output we parse below: the "Nothing to
    # do." / "N packages to upgrade" strings are translated on a non-English system,
    # and matching the English text keeps the change-detection reliable everywhere.
    # (`sudo env VAR=…` sets it in the child cleanly, regardless of sudoers env rules.)
    run_system_upgrade
    # Repo resilience: a repo-scoped failure (bad signature / unreachable / corrupt
    # metadata on ONE source) need not sink the whole run. Only probe when we
    # weren't already told which to skip (a --skip-repo run already named them —
    # probing again would be pointless and would mask a genuinely different error)
    # and the failure actually looks repo-scoped (disk-full/conflict are not).
    systemic_repo_fail=false
    if ! $ok && (( ${#SKIP_REPOS[@]} == 0 )) && repo_scoped_failure; then
        mapfile -t failing < <(find_failing_repos)
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
            up=$(grep -oiE '[0-9]+ packages? to upgrade' "$SYS_LOG" | tail -1 | grep -oE '[0-9]+' | head -1)
            ins=$(grep -oiE '[0-9]+ to install' "$SYS_LOG" | tail -1 | grep -oE '[0-9]+' | head -1)
            SYS_COUNT=$(( ${up:-0} + ${ins:-0} ))
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
    else
        # Turn the most common zypper failures into one plain-English line.
        hint=""
        if $systemic_repo_fail; then
            hint="Several repositories are failing at once — likely a network or system problem, not a single bad source. Check your connection and retry."
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
    rm -f "$SYS_LOG"
fi

# ---------------------------------------------------------------------------
# Step: Flatpak (user scope needs no root; system scope reuses cached sudo)
# ---------------------------------------------------------------------------
if step_selected flatpak; then
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
if step_selected firmware; then
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
if step_selected orphans; then
    begin_step orphans
    mapfile -t UNNEEDED < <(sudo zypper --non-interactive packages --unneeded 2>/dev/null \
        | awk -F'|' 'NR>2 && $3 !~ /^[[:space:]]*$/ {gsub(/ /,"",$3); print $3}')
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
    ORPHAN_COUNT=$(sudo zypper --non-interactive packages --orphaned 2>/dev/null \
        | awk -F'|' 'NR>2 && $3 !~ /^[[:space:]]*$/' | wc -l)
    if ((ORPHAN_COUNT > 0)); then
        echo
        echo "Note: $ORPHAN_COUNT package(s) have no active repository (possibly"
        echo "installed by hand). Left in place — review with:  zypper packages --orphaned"
    fi
fi

# ---------------------------------------------------------------------------
# Step: clean the zypper package cache
# ---------------------------------------------------------------------------
if step_selected cache; then
    begin_step cache
    # Measure the package cache before/after the clean so we can report what it
    # freed — the cache step is otherwise the one task with no visible payoff.
    # du needs root for some subdirs; this step's sudo credential is already warm.
    cache_before=$(sudo du -sB1 /var/cache/zypp 2>/dev/null | awk '{print $1}')
    if sudo zypper --non-interactive clean --all; then
        end_step cache ok
        cache_after=$(sudo du -sB1 /var/cache/zypp 2>/dev/null | awk '{print $1}')
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
    [[ $? -eq 102 ]] && { REBOOT="yes"; REBOOT_REASON="core packages or the kernel were updated"; }
fi
if [[ "$REBOOT" == "no" ]] && $FW_CHANGED; then
    # Firmware changes generally need a reboot to take effect.
    REBOOT="yes"
    REBOOT_REASON="firmware was updated"
fi
# Package-only changes (no kernel/core-lib bump, no firmware) do NOT force a
# reboot — the service-restart step below offers the lighter alternative.
marker INSTALLED "${SYS_COUNT}|$($SYS_CHANGED && echo yes || echo no)|$($FW_CHANGED && echo yes || echo no)"
marker REBOOT "$REBOOT"

# ---------------------------------------------------------------------------
# Services running against replaced libraries. `zypper ps -sss` prints just the
# affected systemd service names. When a full reboot is NOT required, restarting
# these lets the user pick up the new libraries without rebooting.
# ---------------------------------------------------------------------------
SERVICES=""
if $SYS_CHANGED && [[ "$REBOOT" == "no" ]] && command -v zypper &>/dev/null; then
    SERVICES=$(sudo zypper ps -sss 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')
    [[ -n "$SERVICES" ]] && marker SERVICES "$SERVICES"
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
else
    echo "  All selected steps completed cleanly."
    marker DONE "ok"
fi
if [[ "$REBOOT" == "yes" ]]; then
    echo
    echo "  ! A REBOOT is recommended — $REBOOT_REASON."
elif [[ -n "$SERVICES" ]]; then
    echo
    echo "  ! No reboot needed, but these services should restart to use the new"
    echo "    libraries:  $SERVICES"
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
