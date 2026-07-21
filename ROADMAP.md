# OneUp Roadmap

Deferred work, follow-ups, and ideas for OneUp. Shipped items move to
`CHANGELOG.md`; this file tracks what's still open.

## Backlog

- 📋 [ONEUP-0001] **Add `set -uo pipefail` strict mode to update_system.sh.**
  Deferred from the audit: -e must NOT be added (it fights the deliberate `|| ok=false` continue-on-failure design). Add `-uo pipefail` only, after auditing every expansion is `:-`/`:+` guarded (REBOOT, SERVICES, SYS_COUNT, etc.), and run the full tests/run-tests.sh suite to confirm no pipeline regressions.
  **Layman:** Make the update script fail fast on typos/unset variables instead of silently continuing.
  Kind: refactor.
  Source: indie-review-2026-07-21 engine-lane LOW.

- ✅ [ONEUP-0002] **Add a CI test gate that runs tests/run-tests.sh before the release build.**
  Only release.yml exists and it builds the AppImage on a v* tag without running the suite. Add a push/PR workflow (or a step before the build job) that runs tests/run-tests.sh. Note the §6 CI-minutes policy when choosing triggers.
  **Layman:** Right now a release can ship without the engine tests ever running in CI.
  Kind: test.
  Source: indie-review-2026-07-21 packaging-lane INFO.
  Resolved (2026-07-21): release.yml now runs tests/run-tests.sh before the AppImage build, and local-CI.sh runs the same suite pre-push.

- 📋 [ONEUP-0003] **Close remaining engine test-coverage gaps from the indie review.**
  Not covered yet: orphans step (autoremove + report-only orphan count); --check performs NO privileged auth (sudo-sentinel test); keep-alive cleanup on SIGINT/SIGTERM leaves no orphan process; needs-rebooting returning a non-102 non-zero (e.g. lock held) must NOT advise reboot; @@INSTALLED@@ field layout pinned positionally by the GUI. (Firmware fail/success, continue-on-failure, empty-steps, and locale were added in the 2026-07-21 audit.)
  **Layman:** A few update behaviours still have no automated test.
  Kind: test.
  Source: indie-review-2026-07-21 engine-lane.

- 📋 [ONEUP-0004] **Re-test Python 3.14 for the AppImage build when PySide6 ships 3.14 wheels.**
  release.yml pins python-version 3.13 (not 3.14) pending confirmation that PySide6 publishes 3.14 wheels — see docs/standards/dependencies.md ledger. When newer wheels exist, bump and delete the ledger row.
  **Layman:** We're one Python version behind on purpose until the GUI toolkit supports the newest one.
  Kind: chore.
  Source: dependency-standard 2026-07-21.

- 📋 [ONEUP-0005] **Decide refresh-failure semantics for the system step (dup on stale metadata).**
  update_system.sh: when `zypper refresh` fails, `ok=false` but `dup` still runs; a dup that then succeeds is recorded fail with SYS_CHANGED unset, so real changes get no reboot/service advice. Errs on the SAFE side (never a false reboot), hence deferred. Options: abort the step before dup when refresh failed, or evaluate change-detection on the dup exit code independently of the refresh result. Pick one and add a test.
  **Layman:** If the repo refresh fails but the upgrade still installs things, the app currently says the step failed and skips the reboot advice.
  Kind: enhancement.
  Source: indie-review-2026-07-21 loop2 engine-lane LOW.

- ✅ [ONEUP-0006] **Add a version-lockstep guard (bump recipe or CI grep) for the six version sites.**
  No .claude/bump.json (the /bump skill expects one) and no CI check that APP_VERSION, spec Version:+%changelog, _service versionformat+revision, metainfo <release>, and CHANGELOG all agree. A forgotten APP_VERSION would make the self-update check nag every user. Add a bump.json recipe with a post-check, or a tiny CI grep asserting all six agree.
  **Layman:** The version number lives in six files that must match; nothing stops one being forgotten on a release.
  Kind: chore.
  Source: indie-review-2026-07-21 loop2 packaging-lane LOW.
  Resolved (2026-07-21): local-CI.sh includes a version-lockstep gate that fails if any of the six version sites disagree (run pre-push via githooks/pre-push).
