#!/usr/bin/env bash
#
# One-command OneUp release. Does the whole thing:
#   1. bump every version site to X.Y.Z (./bump.py, from CHANGELOG [Unreleased]),
#   2. gate with ./local-CI.sh (tests, lint, validation, version lockstep),
#   3. commit, tag vX.Y.Z, push to GitHub — which builds the AppImage and publishes
#      the release (and the in-app update check then points users at it),
#   4. update the OBS package home:milnet:oneup/oneup via osc — which rebuilds the
#      zypper RPM so repo users get it on their next `zypper up`,
#   5. wait for GitHub's build, sign the AppImage on this PC and upload the signature,
#      without which no installed AppImage is offered the update (ONEUP-0112 §4.9).
#
# Usage:
#   ./release.sh X.Y.Z               full release (GitHub + OBS + signature)
#   ./release.sh X.Y.Z --no-obs      GitHub and signature only (OBS later / by hand)
#   ./release.sh --sign-only X.Y.Z   sign an existing release again, after a moved tag
#
# Prereqs: a clean tree on main, your changes already written under CHANGELOG's
# ## [Unreleased] section, a configured `osc` (for OBS), `gh` signed in, and the
# signing key at ~/.config/oneup-release/signing.key, or wherever $ONEUP_SIGNING_KEY
# points (made once with `python3 packaging/sign-release.py --generate`).
set -uo pipefail
cd "$(dirname "$0")" || exit 1

die() { echo "release: $*" >&2; exit 1; }

sign_only=false
if [[ "${1:-}" == --sign-only ]]; then
    sign_only=true
    shift
fi
ver=${1:-}
[[ "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || die "usage: ./release.sh X.Y.Z [--no-obs]  or  ./release.sh --sign-only X.Y.Z"
do_obs=true
for arg in "${@:2}"; do    # every option, not just the second word (ONEUP-0186)
    case "$arg" in
        --no-obs) $sign_only && die "--sign-only takes no other option"; do_obs=false ;;
        *)        die "unknown option $arg (expected --no-obs)" ;;
    esac
done

# The six version sites live in these five files, and they are all the release commit
# may carry (docs/standards/workflow.md §5.1).
bumped=(oneup/__init__.py packaging/rpm/oneup.spec packaging/obs/_service
        data/za.co.antsprojectshub.OneUp.metainfo.xml CHANGELOG.md)

# The OBS projects that carry the oneup package. The old location, home:milnet, had its
# last update at 2.0.0 (packaging/obs/README.md).
obs_projects=(home:milnet:oneup)

# The OBS checkout is removed however the script ends, an interrupt included, and only
# ever when it was actually made.
work=""
cleanup() { [[ -n "$work" && -d "$work" ]] && rm -rf -- "$work"; }
# The download is signed in a folder of its own: the .sig is not git-ignored, and an
# untracked file in the tree stops the next release's clean-tree check.
sigdir=""
trap 'cleanup; [[ -n "$sigdir" && -d "$sigdir" ]] && rm -rf -- "$sigdir"' EXIT
trap 'exit 130' INT TERM

red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }

key="${ONEUP_SIGNING_KEY:-$HOME/.config/oneup-release/signing.key}"

# Before anything changes: is the signing key here, and is it the private half of the
# public key every installed AppImage checks against? A missing or mismatched key
# would otherwise surface only after the tag is pushed, as a release no AppImage is
# offered. sign-release.py prints only the answer, never key material.
check_signing_key() {
    echo "==> Checking the signing key"
    [[ -f "$key" ]] || die "no signing key at $key — make one with 'python3 packaging/sign-release.py --generate', or point \$ONEUP_SIGNING_KEY at it"
    python3 packaging/sign-release.py --check-key --key "$key" \
        || die "the signing key does not match oneup/gui/update_key.py's public key — not releasing"
}

# Wait for v$ver's Release build, then sign its AppImage, verify the signature
# against the COMMITTED public key — the check every AppImage makes — and upload it.
# --clobber replaces the .sig a moved tag left behind. Returns non-zero on any failure.
sign_release() {
    local sha run
    local asset=OneUp-x86_64.AppImage
    echo "==> Signing the AppImage for v$ver"
    if [[ ! -f "$key" ]]; then
        red "   No signing key at $key — make one with 'python3 packaging/sign-release.py --generate'."
        return 1
    fi
    command -v gh >/dev/null 2>&1 || { red "   gh is not installed."; return 1; }
    sha=$(git rev-parse "v$ver^{commit}") || return 1
    # The run appears a few seconds after the push.
    for _ in $(seq 1 30); do
        run=$(gh run list --workflow release.yml --commit "$sha" --limit 1 \
                  --json databaseId -q '.[0].databaseId' 2>/dev/null)
        [[ -n "$run" ]] && break
        sleep 10
    done
    [[ -n "$run" ]] || { red "   No Release workflow run found for v$ver."; return 1; }
    echo "   Waiting for GitHub to build the AppImage (run $run)…"
    gh run watch "$run" --exit-status >/dev/null \
        || { red "   The Release workflow failed, so there is no AppImage to sign."; return 1; }
    sigdir=$(mktemp -d) || return 1
    gh release download "v$ver" --pattern "$asset" --dir "$sigdir" \
        || { red "   Couldn't download $asset from the v$ver release."; return 1; }
    python3 packaging/sign-release.py --version "$ver" --key "$key" "$sigdir/$asset" \
        || { red "   Signing failed."; return 1; }
    python3 packaging/sign-release.py --verify --version "$ver" "$sigdir/$asset" \
        || { red "   The signature does not verify against oneup/gui/update_key.py's public key."; return 1; }
    gh release upload "v$ver" "$sigdir/$asset.sig" --clobber \
        || { red "   Couldn't upload the signature."; return 1; }
    echo "   Signed and uploaded $asset.sig."
}

if $sign_only; then
    git rev-parse "v$ver" >/dev/null 2>&1 || die "there is no tag v$ver"
    check_signing_key
    sign_release || { red "release: v$ver is NOT signed — no AppImage will be offered it."; exit 4; }
    exit 0
fi

[[ -z "$(git status --porcelain)" ]] || die "working tree not clean — commit or stash first"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "main" ]] || die "not on the main branch"
git rev-parse "v$ver" >/dev/null 2>&1 && die "tag v$ver already exists"
check_signing_key

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
$do_obs && target="$target, and update OBS (${obs_projects[*]})"
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
    obs_updated=true
    for proj in "${obs_projects[@]}"; do
        echo "==> Updating OBS package $proj/oneup"
        if ! command -v osc >/dev/null 2>&1; then
            echo "   osc not installed — re-upload _service + oneup.spec via the web UI (packaging/obs/README.md)."
            obs_updated=false
            continue
        fi
        cleanup
        work=$(mktemp -d) || work=""
        if ( cd "$work" && osc checkout "$proj" oneup >/dev/null 2>&1 ); then
            cp packaging/obs/_service packaging/rpm/oneup.spec "$work/$proj/oneup/"
            # `osc add` stays out of the && chain: on a file the checkout already
            # tracks some osc versions error rather than warn, and that must not skip
            # the commit. Kept for a file that is genuinely new (ONEUP-0255).
            if ( cd "$work/$proj/oneup" \
                 && { osc add _service oneup.spec >/dev/null 2>&1 || true; } \
                 && osc commit -m "oneup $ver" ); then
                echo "   OBS updated — rebuild triggered."
            else
                echo "   osc commit failed — re-upload _service + oneup.spec via the web UI (packaging/obs/README.md)."
                obs_updated=false
            fi
        else
            echo "   osc checkout failed — re-upload _service + oneup.spec via the web UI (packaging/obs/README.md)."
            obs_updated=false
        fi
    done
fi

# After OBS, --no-obs included, so neither failure skips the other (ONEUP-0112 §4.9).
signed=true
sign_release || signed=false

# A release whose OBS half failed is not a clean release, and exiting 0 with
# "Released" said it was (ONEUP-0186). GitHub has it either way; say what is left.
obs_done=true
$do_obs && [[ "${obs_updated:-}" != true ]] && obs_done=false

echo
# An unsigned release is offered to no AppImage, so its exit (4) wins over OBS's (3).
if ! $signed; then
    red "==> Released $ver, but the AppImage is NOT signed — fix that, then run ./release.sh --sign-only $ver"
    $obs_done || echo "   OBS was NOT updated either — do that by hand (see above)."
    exit 4
fi
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
