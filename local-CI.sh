#!/usr/bin/env bash
#
# Local CI — run this before every push so failures are caught here, not on GitHub.
#
# It gates on the same test suite GitHub CI runs, plus checks CI doesn't (lint,
# packaging validation, version lockstep) — all best-effort: a gate whose tool
# isn't installed is skipped, never silently passed. The AppImage build
# (packaging/appimage/build-appimage.sh — the same step the release workflow runs)
# is opt-in via --full, because appimagetool downloads its runtime from GitHub on
# every run and can stall on a slow/filtered link (e.g. a VPN). GitHub CI builds and
# verifies the AppImage on every tag push, so the local build is a convenience.
#
# Usage:
#   ./local-CI.sh          fast gates — tests, lint, packaging validation, version
#                          lockstep (seconds). The reliable pre-push check.
#   ./local-CI.sh --full   also run the AppImage build (wrapped in a 10-min timeout).
#
# A pre-push hook (githooks/pre-push) runs the fast gates automatically before a push.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

FULL=false
[[ "${1:-}" == "--full" ]] && FULL=true

fail=0
step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()   { printf '  \033[32mok\033[0m   %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=1; }
skip() { printf '  --   skip %s (%s)\n' "$1" "$2"; }

# --- engine test suite (same script CI should gate on) ----------------------
step "Engine test suite"
if bash tests/run-tests.sh >/tmp/local-ci-tests.log 2>&1; then
    ok "tests/run-tests.sh — $(grep -oE 'Passed: [0-9]+   Failed: [0-9]+' /tmp/local-ci-tests.log | tail -1)"
else
    bad "tests/run-tests.sh"; tail -25 /tmp/local-ci-tests.log
fi

# --- Python syntax ----------------------------------------------------------
step "Python compile (updater.py)"
if python3 -m py_compile updater.py bump.py; then ok "py_compile updater.py bump.py"; else bad "py_compile"; fi

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
    if ruff check . --select F,B --exclude screenshots -q; then ok "ruff (F,B bug-class)"
    else bad "ruff (F,B bug-class)"; fi
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

# --- version lockstep (the six sites CLAUDE.md documents) -------------------
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
