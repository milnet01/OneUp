#!/usr/bin/env bash
#
# Local CI — run this before every push so failures are caught here, not on GitHub.
#
# It gates on the same test suite GitHub CI runs, plus checks CI doesn't (lint,
# packaging validation, version lockstep, documentation) — all best-effort: a gate
# whose tool isn't installed is skipped, never silently passed. The AppImage build
# (packaging/appimage/build-appimage.sh — the same step the release workflow runs)
# is opt-in via --full, because appimagetool downloads its runtime from GitHub on
# every run and can stall on a slow/filtered link (e.g. a VPN). GitHub CI builds and
# verifies the AppImage on every tag push, so the local build is a convenience.
#
# Usage:
#   ./local-CI.sh          fast gates — tests, lint, packaging validation, version
#                          lockstep, documentation (seconds). The reliable pre-push check.
#   ./local-CI.sh --full   also run the AppImage build (wrapped in a 10-min timeout).
#   ./local-CI.sh --docs   ONLY the gates that can read a markdown file — the version
#                          lockstep (CHANGELOG.md is one of the six sites), bump.py's
#                          functional test (bump rewrites the CHANGELOG heading and both
#                          compare links) and tests/docs-check.py. Measured under a second
#                          all together, against ~90 s for the full run.
#
# A pre-push hook (githooks/pre-push) runs the fast gates automatically before a push, and
# picks --docs when every path in the push ends in .md (ONEUP-0114). The hook decides the
# MODE; this script stays the one place that says what each gate is.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

FULL=false
DOCS=false
case "${1:-}" in
    --full) FULL=true ;;
    --docs) DOCS=true ;;
    "")     ;;
    *)      printf 'local-CI: unknown argument %s (expected --full or --docs)\n' "$1" >&2; exit 2 ;;
esac

fail=0
step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()   { printf '  \033[32mok\033[0m   %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=1; }
skip() { printf '  --   skip %s (%s)\n' "$1" "$2"; }

# --- engine test suite (same script CI should gate on) ----------------------
# ONEUP_TEST_NETWORK=1 opts in to the network-dependent checks (ONEUP-0094 T-1: the
# download-recovery host is still served). This is the run that owns them — the release
# workflow deliberately does not opt in, so it cannot be failed by somebody else's outage.
#
# The default is honoured rather than forced, because githooks/pre-push runs THIS script
# and so inherited the opt-in it is documented as declining: an openSUSE CDN outage failed
# a push, which is the outcome the split exists to prevent. The hook passes 0 (ONEUP-0097).
if ! $DOCS; then

step "Engine test suite"
if ONEUP_TEST_NETWORK="${ONEUP_TEST_NETWORK:-1}" bash tests/run-tests.sh >/tmp/local-ci-tests.log 2>&1; then
    ok "tests/run-tests.sh — $(grep -oE 'Passed: [0-9]+   Failed: [0-9]+' /tmp/local-ci-tests.log | tail -1)"
else
    bad "tests/run-tests.sh"; tail -25 /tmp/local-ci-tests.log
fi

# --- headless GUI smoke test ------------------------------------------------
# Constructs the PySide6 window offscreen and feeds it engine markers. Exit 77
# means PySide6 isn't installed here — a skip, not a failure (matches the
# engine's skip-cleanly-for-absent-tools convention).
step "GUI smoke test (offscreen)"
python3 tests/gui-smoke.py >/tmp/local-ci-gui.log 2>&1
rc=$?
if [[ $rc -eq 0 ]]; then
    ok "tests/gui-smoke.py — $(grep -oE 'Passed: [0-9]+   Failed: [0-9]+' /tmp/local-ci-gui.log | tail -1)"
elif [[ $rc -eq 77 ]]; then
    skip "tests/gui-smoke.py" "PySide6 not installed"
else
    bad "tests/gui-smoke.py"; tail -25 /tmp/local-ci-gui.log
fi

# --- Python syntax ----------------------------------------------------------
step "Python compile (updater.py)"
if python3 -m py_compile updater.py bump.py; then ok "py_compile updater.py bump.py"; else bad "py_compile"; fi

fi   # end of the first code-gate block skipped by --docs

# --- bump.py functional test ------------------------------------------------
# NOT skipped by --docs: bump.py rewrites the CHANGELOG heading and both compare links, so
# a malformed [Unreleased] is a markdown edit that fails here and nowhere else.
# Runs a real bump in a throwaway repo copy and asserts every version site
# advances (incl. the CHANGELOG [Unreleased] compare base). Stdlib-only, exit 0/1.
step "bump.py functional test"
if python3 tests/bump-test.py >/tmp/local-ci-bump.log 2>&1; then
    ok "tests/bump-test.py — $(grep -oE 'Passed: [0-9]+   Failed: [0-9]+' /tmp/local-ci-bump.log | tail -1)"
else
    bad "tests/bump-test.py"; tail -25 /tmp/local-ci-bump.log
fi

if ! $DOCS; then

# --- lint (best-effort) -----------------------------------------------------
step "Lint"
if command -v shellcheck >/dev/null 2>&1; then
    # SC2001 is a documented false positive (sed used deliberately for per-line
    # munging) — see .ants_review_falsepos.jsonl.
    if shellcheck -e SC2001 update_system.sh tests/run-tests.sh \
            packaging/appimage/build-appimage.sh local-CI.sh release.sh githooks/pre-push; then
        ok "shellcheck"; else bad "shellcheck"; fi
else skip "shellcheck" "not installed"; fi
if command -v ruff >/dev/null 2>&1; then
    if ruff check . -q; then ok "ruff (pyproject.toml rule set)"
    else bad "ruff (pyproject.toml rule set)"; fi
else skip "ruff" "not installed"; fi

# --- packaging validation (best-effort) -------------------------------------
step "Packaging validation"
if command -v desktop-file-validate >/dev/null 2>&1; then
    if desktop-file-validate data/za.co.antsprojectshub.OneUp.desktop; then ok "desktop-file-validate"
    else bad "desktop-file-validate"; fi
else skip "desktop-file-validate" "not installed"; fi
if command -v appstreamcli >/dev/null 2>&1; then
    if appstreamcli validate --no-net data/za.co.antsprojectshub.OneUp.metainfo.xml \
            >/tmp/local-ci-appstream.log 2>&1; then ok "appstreamcli validate"
    else bad "appstreamcli validate"; cat /tmp/local-ci-appstream.log; fi
else skip "appstreamcli" "not installed"; fi

fi   # end of the code gates skipped by --docs

# --- version lockstep (the six sites docs/standards/workflow.md §5.1 documents) ---
# NOT skipped by --docs: CHANGELOG.md is markdown AND one of the six sites.
step "Version lockstep (six sites must agree)"
v_py=$(grep -oP 'APP_VERSION = "\K[^"]+' updater.py)
v_spec=$(grep -oP '^Version:\s+\K\S+' packaging/rpm/oneup.spec)
v_speclog=$(grep -oP '^\* .* - \K[0-9]+\.[0-9]+\.[0-9]+' packaging/rpm/oneup.spec | head -1)
v_fmt=$(grep -oP 'versionformat">\K[^<]+' packaging/obs/_service)
v_rev=$(grep -oP 'revision">v?\K[^<]+' packaging/obs/_service)
v_meta=$(grep -oP '<release version="\K[^"]+' data/za.co.antsprojectshub.OneUp.metainfo.xml | head -1)
v_chg=$(grep -oP '^## \[\K[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md | head -1)
printf '  updater.py=%s spec=%s spec%%changelog=%s _service.fmt=%s _service.rev=%s metainfo=%s CHANGELOG=%s\n' \
    "$v_py" "$v_spec" "$v_speclog" "$v_fmt" "$v_rev" "$v_meta" "$v_chg"
if [[ "$v_py" == "$v_spec" && "$v_py" == "$v_speclog" && "$v_py" == "$v_fmt" \
      && "$v_py" == "$v_rev" && "$v_py" == "$v_meta" && "$v_py" == "$v_chg" ]]; then
    ok "all six version sites = $v_py"
else
    bad "version sites disagree (see line above)"
fi

# --- documentation (the rules of docs/standards/documentation.md a script can settle) ---
# Reports, never repairs (workflow.md §6.1): it names the file, the line and the rule, and
# the author decides what the right text is.
step "Documentation"
if python3 tests/docs-check.py >/tmp/local-ci-docs.log 2>&1; then
    ok "tests/docs-check.py — $(grep -oE 'Checked: [0-9]+   Failed: [0-9]+' /tmp/local-ci-docs.log | tail -1)"
else
    bad "tests/docs-check.py"; cat /tmp/local-ci-docs.log
fi

# --- AppImage build (opt-in; also built + verified by GitHub CI on a tag push) ---
if $FULL; then
    step "AppImage build (--full; same step the release workflow runs)"
    # appimagetool downloads its runtime from GitHub each run, which can stall on a
    # slow/filtered link — cap it so local CI fails cleanly instead of hanging.
    if timeout 600 bash packaging/appimage/build-appimage.sh; then
        ok "build-appimage.sh → OneUp-x86_64.AppImage"
    else
        rc=$?
        if [[ $rc -eq 124 ]]; then
            bad "build-appimage.sh timed out after 10 min — likely the appimagetool runtime download stalled (network/VPN), not a code fault"
        else
            bad "build-appimage.sh (exit $rc)"
        fi
    fi
else
    step "AppImage build — skipped (run with --full; GitHub CI builds + verifies it on a tag push)"
fi

# --- verdict ----------------------------------------------------------------
echo
if [[ $fail -eq 0 ]]; then
    printf '\033[32m✔ Local CI passed — safe to push.\033[0m\n'
else
    printf '\033[31m✗ Local CI FAILED — fix the above before pushing.\033[0m\n'
fi
exit $fail
