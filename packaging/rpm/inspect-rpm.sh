#!/usr/bin/env bash
#
# Build OneUp's RPM from a commit and look inside it, without installing it.
#
# The package is built from what git holds at REF, not from the working tree, so an
# uncommitted change is not in it. The spec file is taken from REF too. The build runs
# in a scratch directory inside the repository's .git directory — on the repository's
# own disk, never /tmp, which is RAM on the development machine — and the scratch is
# removed however the script ends.
#
# Usage:
#   packaging/rpm/inspect-rpm.sh [--ref REF] list         every path the RPM installs
#   packaging/rpm/inspect-rpm.sh [--ref REF] cat PATH     print one installed file
#
# REF defaults to HEAD. PATH is an installed path as `list` prints it, such as
# /usr/share/oneup/updater.py.
#
# Deps: git, rpmbuild, rpm, rpm2cpio, cpio — and the spec's BuildRequires on the
# build host.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1     # repo root

die() { echo "inspect-rpm: $*" >&2; exit 1; }
usage="usage: packaging/rpm/inspect-rpm.sh [--ref REF] list | cat PATH"

ref=HEAD
if [[ "${1:-}" == "--ref" ]]; then
    [[ -n "${2:-}" ]] || die "$usage"
    ref=$2
    shift 2
fi
action=${1:-}
case "$action" in
    list) [[ $# -eq 1 ]] || die "$usage" ;;
    cat)  [[ $# -eq 2 ]] || die "$usage"; want=$2 ;;
    *)    die "$usage" ;;
esac

for tool in git rpmbuild rpm rpm2cpio cpio; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is not installed"
done
commit=$(git rev-parse --verify --quiet "$ref^{commit}") || die "no commit called $ref"
spec=$(git show "$commit:packaging/rpm/oneup.spec" 2>/dev/null) \
    || die "$ref has no packaging/rpm/oneup.spec"
version=$(grep -oP '^Version:\s+\K\S+' <<<"$spec") || die "no Version: line in $ref's spec"

# The scratch is removed however the script ends, an interrupt included, and only ever
# when it was actually made.
work=""
cleanup() { [[ -n "$work" && -d "$work" ]] && rm -rf -- "$work"; }
trap cleanup EXIT
trap 'exit 130' INT TERM

gitdir=$(git rev-parse --path-format=absolute --git-common-dir) || die "not in a git repository"
work=$(mktemp -d "$gitdir/rpm-scratch.XXXXXX") || die "cannot make a scratch directory"
mkdir -p "$work/SOURCES" "$work/SPECS"
printf '%s\n' "$spec" >"$work/SPECS/oneup.spec"
git archive --format=tar.gz --prefix="oneup-$version/" \
    -o "$work/SOURCES/oneup-$version.tar.gz" "$commit" || die "git archive failed"

echo "==> Building oneup $version from ${commit:0:7}" >&2
if ! rpmbuild -bb --define "_topdir $work" "$work/SPECS/oneup.spec" >"$work/build.log" 2>&1; then
    tail -n 30 "$work/build.log" >&2
    die "rpmbuild failed (the last 30 lines of its log are above)"
fi
rpms=("$work"/RPMS/noarch/oneup-"$version"-*.noarch.rpm)
[[ -f "${rpms[0]}" ]] || die "rpmbuild reported success but left no oneup-$version RPM"

case "$action" in
    list) rpm -qlp "${rpms[0]}" ;;
    cat)
        # cpio prints nothing and exits 0 for a path the archive lacks, so ask the
        # package first rather than reading silence as an empty file.
        rpm -qlp "${rpms[0]}" | grep -Fxq -- "$want" \
            || die "$want is not in the package (run 'list' to see what is)"
        rpm2cpio "${rpms[0]}" | cpio -i --quiet --to-stdout -- ".$want" ;;
esac
