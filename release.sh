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
[[ "${2:-}" == "--no-obs" ]] && do_obs=false

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
git add -A
git commit -q -m "OneUp $ver"
git tag "v$ver"
git push origin main "v$ver" || die "git push failed"
echo "   GitHub is building the AppImage and publishing the v$ver release."

if $do_obs; then
    echo "==> Updating OBS package home:milnet/oneup"
    if ! command -v osc >/dev/null 2>&1; then
        echo "   osc not installed — re-upload _service + oneup.spec via the web UI (packaging/obs/README.md)."
    else
        work=$(mktemp -d)
        if ( cd "$work" && osc checkout home:milnet oneup >/dev/null 2>&1 ); then
            cp packaging/obs/_service packaging/rpm/oneup.spec "$work/home:milnet/oneup/"
            if ( cd "$work/home:milnet/oneup" \
                 && osc add _service oneup.spec >/dev/null 2>&1 \
                 && osc commit -m "oneup $ver" ); then
                echo "   OBS updated — rebuild triggered."
            else
                echo "   osc commit failed — re-upload _service + oneup.spec via the web UI (packaging/obs/README.md)."
            fi
        else
            echo "   osc checkout failed — re-upload _service + oneup.spec via the web UI (packaging/obs/README.md)."
        fi
        rm -rf "$work"
    fi
fi

echo
echo "==> Released $ver 🎉"
echo "   AppImage:  https://github.com/milnet01/OneUp/releases/tag/v$ver  (once CI finishes)"
$do_obs && echo "   zypper:    sudo zypper refresh && sudo zypper install oneup"
