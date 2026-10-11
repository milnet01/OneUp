#!/usr/bin/env bash
#
# One-command OneUp release. Does the whole thing:
#   1. bump every version site to X.Y.Z (./bump.py, from CHANGELOG [Unreleased]),
#   2. gate with ./local-CI.sh (tests, lint, validation, version lockstep),
#   3. commit, tag vX.Y.Z, push to GitHub — which builds the AppImage and publishes
#      the release (and the in-app update check then points users at it),
#   4. update the OBS package home:milnet/oneup via osc — which rebuilds the zypper
#      RPM so repo users get it on their next `zypper up`.
#
# Usage:
#   ./release.sh X.Y.Z            full release (GitHub + OBS)
#   ./release.sh X.Y.Z --no-obs   GitHub only (do the OBS step later / by hand)
#
# Prereqs: a clean tree on main, your changes already written under CHANGELOG's
# ## [Unreleased] section, and (for the OBS step) a configured `osc`.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

die() { echo "release: $*" >&2; exit 1; }

ver=${1:-}
[[ "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "usage: ./release.sh X.Y.Z [--no-obs]"
do_obs=true
for arg in "${@:2}"; do    # every option, not just the second word (ONEUP-0186)
    case "$arg" in
        --no-obs) do_obs=false ;;
        *)        die "unknown option $arg (expected --no-obs)" ;;
    esac
done

# The six version sites live in these five files, and they are all the release commit
# may carry (docs/standards/workflow.md §5.1).
bumped=(oneup/__init__.py packaging/rpm/oneup.spec packaging/obs/_service
        data/za.co.antsprojectshub.OneUp.metainfo.xml CHANGELOG.md)

# The OBS checkout is removed however the script ends, an interrupt included, and only
# ever when it was actually made.
work=""
cleanup() { [[ -n "$work" && -d "$work" ]] && rm -rf -- "$work"; }
trap cleanup EXIT
trap 'exit 130' INT TERM

[[ -z "$(git status --porcelain)" ]] || die "working tree not clean — commit or stash first"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "main" ]] || die "not on the main branch"
git rev-parse "v$ver" >/dev/null 2>&1 && die "tag v$ver already exists"

echo "==> Bumping to $ver"
./bump.py "$ver" || die "bump failed (is there a non-empty ## [Unreleased] in CHANGELOG.md?)"

echo "==> Local CI"
if ! ./local-CI.sh; then
    echo "release: local CI failed — the bump is left in your tree; fix and re-run, or 'git checkout -- .' to discard." >&2
    exit 1
fi

echo
git --no-pager diff --stat
echo
target="commit, tag v$ver and push to GitHub"
$do_obs && target="$target, and update OBS (home:milnet/oneup)"
read -rp "Proceed to $target? [y/N] " ans
[[ "$ans" == [yY] ]] || die "aborted — bump left in your tree ('git checkout -- .' to discard)"

echo "==> Commit, tag, push"
# The clean-tree check ran before the bump, local CI and the prompt. Anything the
# suites wrote, or anything edited while the prompt waited, would otherwise ride into
# the release commit unseen — so the commit takes the bumped files by name, and any
# other change stops the release (ONEUP-0186).
stray=$( { git ls-files --modified --others --exclude-standard; git diff --cached --name-only; } \
         | sort -u | grep -vxF -f <(printf '%s\n' "${bumped[@]}") )
[[ -z "$stray" ]] || die "files changed outside the version bump — not releasing:
$stray"
git add -- "${bumped[@]}"
git commit -q -m "OneUp $ver"
git tag "v$ver"
# --atomic: the branch and the tag land together or not at all. Without it a rejected
# main could still leave the tag on GitHub, and release.yml publishes a tag
# (ONEUP-0186; docs/standards/workflow.md §8's undo assumes nothing reached the remote).
git push --atomic origin main "v$ver" || die "git push failed — nothing was pushed"
echo "   GitHub is building the AppImage and publishing the v$ver release."

if $do_obs; then
    echo "==> Updating OBS package home:milnet/oneup"
    if ! command -v osc >/dev/null 2>&1; then
        echo "   osc not installed — re-upload _service + oneup.spec via the web UI (packaging/obs/README.md)."
    else
        work=$(mktemp -d) || work=""
        if ( cd "$work" && osc checkout home:milnet oneup >/dev/null 2>&1 ); then
            cp packaging/obs/_service packaging/rpm/oneup.spec "$work/home:milnet/oneup/"
            # `osc add` is NOT in the && chain: the checkout above is of an EXISTING
            # package, so both files are already versioned and `add` errors on them.
            # Chained, that short-circuited the commit, so every release after the
            # first reported "osc commit failed" without ever attempting one. It is
            # kept for the case where a file is genuinely new, and its failure is
            # ignored. stderr is no longer discarded — the reason a commit failed is
            # the whole point of the message below.
            if ( cd "$work/home:milnet/oneup" \
                 && { osc add _service oneup.spec >/dev/null 2>&1 || true; } \
                 && osc commit -m "oneup $ver" ); then
                echo "   OBS updated — rebuild triggered."
                obs_updated=true
            else
                echo "   osc commit failed — re-upload _service + oneup.spec via the web UI (packaging/obs/README.md)."
            fi
        else
            echo "   osc checkout failed — re-upload _service + oneup.spec via the web UI (packaging/obs/README.md)."
        fi
    fi
fi

# A release whose OBS half failed is not a clean release, and exiting 0 with
# "Released" said it was (ONEUP-0186). GitHub has it either way; say what is left.
obs_done=true
$do_obs && [[ "${obs_updated:-}" != true ]] && obs_done=false

echo
if ! $obs_done; then
    echo "==> Released $ver to GitHub, but OBS was NOT updated — do that by hand (see above)."
    echo "   AppImage:  https://github.com/milnet01/OneUp/releases/tag/v$ver  (once CI finishes)"
    exit 3
fi
echo "==> Released $ver 🎉"
echo "   AppImage:  https://github.com/milnet01/OneUp/releases/tag/v$ver  (once CI finishes)"
# An `if`, not `$do_obs && echo`: as the last line, a false $do_obs made a successful
# --no-obs release exit 1 (found by the ONEUP-0186 probe).
if $do_obs; then
    echo "   zypper:    sudo zypper refresh && sudo zypper install oneup"
fi
