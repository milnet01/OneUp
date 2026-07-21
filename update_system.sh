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

usage() {
    cat <<EOF
System Updater engine

Usage: $(basename "$0") [--steps=LIST] [--check] [--notify] [--log=FILE] [--help]

  --steps=LIST   Comma-separated steps to run. Default: all.
                 Available: system, flatpak, firmware, orphans, cache
  --check        Read-only: report how many updates are available and exit.
                 Runs WITHOUT root, so it is safe for an unattended timer.
  --notify       With --check, raise a desktop notification when updates exist.
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
#   @@SNAPSHOT@@|id
#   @@CHECK@@|key|count|label            (--check mode: updates available)
#   @@DISK@@|warn|mount|free             (pre-flight: low disk space)
#   @@REPO@@|warn|reason                 (pre-flight: repo health issue)
#   @@HINT@@|plain-English failure hint
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
        # Upgradable packages have a 'v' in zypper's status column.
        n=$(zypper --no-refresh --non-interactive list-updates 2>/dev/null \
            | grep -cE '^v[[:space:]]*\|')
        marker CHECK "system|$n|system package(s)"
        echo "  System packages: $n update(s)"
        (( total += n ))
    fi
    if step_selected flatpak && command -v flatpak &>/dev/null; then
        n=$(( $(flatpak remote-ls --updates --user 2>/dev/null | wc -l) \
            + $(flatpak remote-ls --updates --system 2>/dev/null | wc -l) ))
        marker CHECK "flatpak|$n|Flatpak app(s)"
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
    ( while true; do sudo -n -v 2>/dev/null || true; sleep 50; done ) >/dev/null 2>&1 &
    SUDO_KEEPALIVE=$!
}
cleanup() { [[ -n "$SUDO_KEEPALIVE" ]] && kill "$SUDO_KEEPALIVE" 2>/dev/null; }
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
        marker REPO "warn|duplicate"
    fi
fi

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
    ok=true
    sudo zypper --non-interactive refresh || ok=false
    # Capture the transaction output so we can tell whether anything actually
    # changed (for the summary and the reboot advice), while still streaming it.
    SYS_LOG=$(mktemp)
    # Pin LC_ALL=C on the transaction whose output we parse below: the "Nothing to
    # do." / "N packages to upgrade" strings are translated on a non-English system,
    # and matching the English text keeps the change-detection reliable everywhere.
    # (`sudo env VAR=…` sets it in the child cleanly, regardless of sudoers env rules.)
    if [[ -f /etc/os-release ]] && grep -q "Leap" /etc/os-release; then
        sudo env LC_ALL=C zypper --non-interactive update 2>&1 | tee "$SYS_LOG"
    else
        # Tumbleweed: --allow-vendor-change lets Packman codec packages update
        # cleanly; without it the upgrade stalls on vendor conflicts.
        sudo env LC_ALL=C zypper --non-interactive dup --allow-vendor-change 2>&1 | tee "$SYS_LOG"
    fi
    [[ ${PIPESTATUS[0]} -eq 0 ]] || ok=false
    # Only interpret the transaction output when the step actually SUCCEEDED. A
    # blocked/failed run has no "Nothing to do." line, so treating the else-branch
    # as "packages changed" would falsely trip the reboot advice — the step failed,
    # nothing was installed.
    if $ok; then
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
    else
        # Turn the most common zypper failures into one plain-English line.
        hint=""
        if grep -qiE 'No space left|disk full' "$SYS_LOG"; then
            hint="Ran out of disk space — free some room (clear the package cache, delete old snapshots) and retry."
        elif grep -qiE 'signature|GPG|key.*(expired|reject)' "$SYS_LOG"; then
            hint="A repository signing key looks wrong or expired — run: sudo zypper --gpg-auto-import-keys refresh, then retry."
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
    if sudo zypper --non-interactive clean --all; then
        end_step cache ok
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
echo "  Log saved: $LOG_FILE"
echo "=========================================="

# Non-zero exit if anything failed, so the GUI can colour the run accordingly.
((ERRORS == 0))
