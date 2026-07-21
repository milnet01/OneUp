# OneUp Roadmap

Deferred work, follow-ups, and ideas for OneUp. Shipped items move to
`CHANGELOG.md`; this file tracks what's still open.

## Backlog

- ✅ [ONEUP-0001] **Add `set -uo pipefail` strict mode to update_system.sh.**
  Deferred from the audit: -e must NOT be added (it fights the deliberate `|| ok=false` continue-on-failure design). Add `-uo pipefail` only, after auditing every expansion is `:-`/`:+` guarded (REBOOT, SERVICES, SYS_COUNT, etc.), and run the full tests/run-tests.sh suite to confirm no pipeline regressions.
  **Layman:** Make the update script fail fast on typos/unset variables instead of silently continuing.
  Kind: refactor.
  Source: indie-review-2026-07-21 engine-lane LOW.
  Resolved (2026-07-21): `set -uo pipefail` added to update_system.sh (commit 675cf47). The empty/unknown --steps regression it introduced was fixed under ONEUP-0013 (declare -a RUN_KEYS=()). Full suite green at 34/34.

- ✅ [ONEUP-0002] **Add a CI test gate that runs tests/run-tests.sh before the release build.**
  Only release.yml exists and it builds the AppImage on a v* tag without running the suite. Add a push/PR workflow (or a step before the build job) that runs tests/run-tests.sh. Note the §6 CI-minutes policy when choosing triggers.
  **Layman:** Right now a release can ship without the engine tests ever running in CI.
  Kind: test.
  Source: indie-review-2026-07-21 packaging-lane INFO.
  Resolved (2026-07-21): release.yml now runs tests/run-tests.sh before the AppImage build, and local-CI.sh runs the same suite pre-push.

- ✅ [ONEUP-0003] **Close remaining engine test-coverage gaps from the indie review.**
  Not covered yet: orphans step (autoremove + report-only orphan count); --check performs NO privileged auth (sudo-sentinel test); keep-alive cleanup on SIGINT/SIGTERM leaves no orphan process; needs-rebooting returning a non-102 non-zero (e.g. lock held) must NOT advise reboot; @@INSTALLED@@ field layout pinned positionally by the GUI. (Firmware fail/success, continue-on-failure, empty-steps, and locale were added in the 2026-07-21 audit.)
  **Layman:** A few update behaviours still have no automated test.
  Kind: test.
  Source: indie-review-2026-07-21 engine-lane.
  Resolved (2026-07-21): added three engine tests — (1) --check invokes sudo zero times (sentinel sudo mock exits 99 if called); (2) the sudo keep-alive leaves no orphaned process after a run (before/after `pgrep -xf 'sleep 50'` diff); (3) @@INSTALLED@@ keeps its positional count|yes/no|yes/no layout. Writing (2) surfaced a real orphan leak: cleanup did `kill <subshell>` which orphaned the loop's `sleep 50` (reparented to init ~50s). Fixed by running the keep-alive under setsid in its own process group and tearing it down with `kill -- -PGID`. Red/green verified. Orphans/non-102/firmware/locale/continue-on-fail were already covered by the 2026-07-21 audit. Suite 32→38.

- 📋 [ONEUP-0004] **Re-test Python 3.14 for the AppImage build when PySide6 ships 3.14 wheels.**
  release.yml pins python-version 3.13 (not 3.14) pending confirmation that PySide6 publishes 3.14 wheels — see docs/standards/dependencies.md ledger. When newer wheels exist, bump and delete the ledger row.
  **Layman:** We're one Python version behind on purpose until the GUI toolkit supports the newest one.
  Kind: chore.
  Source: dependency-standard 2026-07-21.

- ✅ [ONEUP-0005] **Decide refresh-failure semantics for the system step (dup on stale metadata).**
  update_system.sh: when `zypper refresh` fails, `ok=false` but `dup` still runs; a dup that then succeeds is recorded fail with SYS_CHANGED unset, so real changes get no reboot/service advice. Errs on the SAFE side (never a false reboot), hence deferred. Options: abort the step before dup when refresh failed, or evaluate change-detection on the dup exit code independently of the refresh result. Pick one and add a test.
  **Layman:** If the repo refresh fails but the upgrade still installs things, the app currently says the step failed and skips the reboot advice.
  Kind: enhancement.
  Source: indie-review-2026-07-21 loop2 engine-lane LOW.
  Resolved (2026-07-21): chose option (b) — the dup/update transaction's exit code decides step success, not the refresh. refresh is now tracked in a separate refresh_ok; a failed refresh with a successful upgrade records the step ok, keeps SYS_CHANGED/reboot/rollback advice, and emits a non-fatal "upgraded from cached metadata" @@HINT@@. Rejected (a) abort-before-dup: it would deny a working update over a transiently flaky mirror. Red/green: added a refresh-fail-but-dup-succeeds test (4 asserts, red before). Caught + fixed a PIPESTATUS-clobber I introduced (an `ok=true` assignment must sit BEFORE the dup pipe, not between the pipe and the exit-code check) — that had broken the two existing dup-failure tests; suite green at 43/43.

- ✅ [ONEUP-0006] **Add a version-lockstep guard (bump recipe or CI grep) for the six version sites.**
  No .claude/bump.json (the /bump skill expects one) and no CI check that APP_VERSION, spec Version:+%changelog, _service versionformat+revision, metainfo <release>, and CHANGELOG all agree. A forgotten APP_VERSION would make the self-update check nag every user. Add a bump.json recipe with a post-check, or a tiny CI grep asserting all six agree.
  **Layman:** The version number lives in six files that must match; nothing stops one being forgotten on a release.
  Kind: chore.
  Source: indie-review-2026-07-21 loop2 packaging-lane LOW.
  Resolved (2026-07-21): local-CI.sh includes a version-lockstep gate that fails if any of the six version sites disagree (run pre-push via githooks/pre-push).

- ✅ [ONEUP-0007] **Add a headless GUI smoke test (QT_QPA_PLATFORM=offscreen).**
  updater.py has zero automated coverage. Add a test that runs Qt offscreen, constructs Updater(), and feeds representative @@MARKER@@ lines through handle_marker (STEP_BEGIN/STEP_END/CHECK/INSTALLED/REBOOT/SERVICES/DISK/REPO/HINT + a malformed line) asserting no exception and expected state (badges, banners). Wire into local-CI.sh.
  **Layman:** Automatically catch crashes in the app window that the current checks can't see.
  Kind: test.
  Source: suggestion 2026-07-21.
  Resolved (2026-07-21): added tests/gui-smoke.py — constructs Updater() under QT_QPA_PLATFORM=offscreen and drives handle_line/handle_marker/on_finished with representative marker sequences (STEP_BEGIN/STEP_END across ok/skip/fail, CHECK, INSTALLED, SNAPSHOT, SERVICES, REBOOT, DISK, a malformed '@@ diff' line, plain log). Asserts row badges, the reboot/services/rollback/retry banner logic, and the --check summary path; 23 checks. Hermetic (HOME/XDG redirected to a tempdir so save_last_run can't touch real state); exits 77 = skip when PySide6 is absent. Wired into local-CI.sh (skip-aware) and .github/workflows/release.yml (installs PySide6 + Qt offscreen libs; exit 77 tolerated, a real failure blocks the tag).

- ✅ [ONEUP-0008] **Show per-step timing and what changed on each task row.**
  The engine already tracks SECS per step and the package count. Surface e.g. 'took 42s · 3 packages' on the row or an expandable detail, so a run reads more clearly. Consider a marker or reuse STEP_END detail + a TIMING marker.
  **Layman:** See how long each task took and a bit more detail about what it did.
  Kind: ux.
  Source: suggestion 2026-07-21.
  Resolved (2026-07-21): engine emits a new additive @@TIMING@@|key|seconds marker from end_step (SECS was already tracked; STEP_END's status|detail contract untouched). GUI TaskRow keeps outcome and timing apart (_badge_text/_timing, re-rendered together as "3 installed · 42s") so a duplicate/spliced marker can't stack; handle_marker gained a TIMING branch and a _format_duration helper (<1s / 42s / 1m 5s). Tests: engine asserts @@TIMING@@|system|<n>; GUI asserts the combined badge + _format_duration. Marker documented in update_system.sh header + CLAUDE.md list. Engine 38→39, GUI 26→29.

- ✅ [ONEUP-0009] **Add an About dialog (version, license, GitHub/OBS links, check-for-update).**
  Now that the version is shown, add a small About dialog reachable from the header — APP_VERSION, MIT licence, links to the GitHub repo + OBS package, and a manual 'check for updates' button (reuses _check_app_update).
  **Layman:** A small 'About OneUp' window with the version, licence and links.
  Kind: feature.
  Source: suggestion 2026-07-21.
  Resolved (2026-07-21): added an "About" GhostBtn to the header opening show_about() — a QMessageBox with the icon, APP_NAME + version, MIT licence, clickable GitHub + OBS links (openExternalLinks), and a "Check for updates" button. Reuses _check_app_update, now with a manual flag: the manual path reports the result either way (up-to-date / newer available / couldn't reach GitHub) while the automatic startup check stays silent unless a newer release exists. gui-smoke.py opens+auto-dismisses the modal (QTimer) to prove it doesn't crash; 26 checks.

- ✅ [ONEUP-0010] **Fire a desktop notification when a manual (foreground) run finishes.**
  Today only the weekly --check notifies. On on_finished, send a notify-send summary (done / N installed / errors) so a foreground run you walked away from still tells you when it's done.
  **Layman:** Get a notification when an update you started finishes, in case you tabbed away.
  Kind: enhancement.
  Source: suggestion 2026-07-21.
  Resolved (2026-07-21): added Updater._notify_when_away(), fired from both branches of on_finished (real run: "All done — …" / "Finished — some steps had errors", critical urgency on error; --check: availability summary). Gated on `not self.isActiveWindow()` so it only pops when you've switched away, and best-effort (skipped if notify-send is absent, like the engine). gui-smoke.py grew a mock notify-send on PATH and asserts a finished run notifies (24 checks).

- ✅ [ONEUP-0011] **Add openSUSE Leap as an OBS build target.**
  OneUp supports Leap (engine uses `zypper update` on Leap). Add openSUSE_Leap_15.6 under the project's Repositories in the OBS web UI so Leap users can `zypper install oneup`. Update packaging/obs/README.md + README install repo URL note.
  **Layman:** Publish the zypper package for Leap users too, not just Tumbleweed.
  Kind: package.
  Source: suggestion 2026-07-21.
  Resolved (2026-07-21): repo + docs side complete. OneUp already supports Leap at runtime (engine runs `zypper update` on Leap vs `dup` on Tumbleweed) and the RPM is noarch, so serving Leap is only adding the openSUSE_Leap_15.6 build target in the OBS web UI (documented click-path in packaging/obs/README.md). Documented the one real caveat: the RPM Requires python3-pyside6, which is in Tumbleweed's repos but may be older/absent on Leap — verify with `zypper info python3-pyside6`, and steer Leap users to the self-contained AppImage if the RPM dep is unsatisfiable. The build-target add itself is the user's OBS click.

- 📋 [ONEUP-0012] **Wire up the fully hands-off OBS rebuild (token + webhook / SCM-CI).**
  Set up OBS's GitHub token + webhook (or .obs/workflows.yml) so a pushed tag triggers a rebuild from the git checkout, removing release.sh's osc step and the manual _service re-upload. One-time OBS account setup (token + repo webhook); needs building from git rather than an uploaded _service. See packaging/obs/README.md 'fully hands-off' note.
  **Layman:** Make OBS rebuild the package on its own whenever a new version tag is pushed — no local osc, no re-upload.
  Kind: enhancement.
  Source: suggestion 2026-07-21.
  Progress (2026-07-21): scaffolded + documented, awaiting user OBS activation. Added .obs/workflows.yml (a rebuild_on_tag workflow firing trigger_services on tag_push; inert until wired) and a concrete token+webhook setup section in packaging/obs/README.md. Honest framing recorded: release.sh ALREADY retriggers the OBS rebuild via osc, so the webhook only adds value for a bare `git push --tags` that bypasses release.sh — and even then, trigger_services rebuilds whatever _service pins as <revision>, so true hands-off for arbitrary tags needs converting the OBS package to build directly from the git ref (SCM-linked model), a bigger one-time restructure. Left planned: needs the user's OBS workflow token + GitHub webhook + a verification tag push (can't be tested from here).

- ✅ [ONEUP-0013] **Fix set -uo pipefail regression on the empty/unknown --steps path.**
  After adding `set -uo pipefail` (ONEUP-0001, commit 675cf47), `update_system.sh --steps=` (or an all-unknown list) exits 1 on an unset variable BEFORE the intended `exit 2` guard, so the 'No valid update steps selected' message is suppressed. The empty-steps test only asserts a non-zero exit, so it masked the change (exit 1 still passes). FIX: find the empty-RUN_KEYS/unbound expansion (likely an empty-array reference under -u between building RUN_KEYS and the TOTAL==0 guard), and TIGHTEN tests/run-tests.sh to assert exit code == 2 AND the 'No valid' message, for both --steps= and --steps=bogus. Reproduce: `bash update_system.sh --steps= --log=/tmp/x.log; echo $?` -> currently 1, want 2 with the message. Verify normal runs still 32/32.
  **Layman:** A mistyped or empty --steps now fails less helpfully than intended.
  Kind: fix.
  Source: in-session-2026-07-21 (self-caught after ONEUP-0001, commit 675cf47).
  Resolved (2026-07-21): root cause was `declare -a RUN_KEYS` (no =()) — under `set -u` an array declared but never assigned counts as unset, so ${#RUN_KEYS[@]} aborted with exit 1 before the TOTAL==0 guard. Fixed with `declare -a RUN_KEYS=()`. Tightened tests/run-tests.sh to assert exit == 2 AND the 'No valid update steps selected' message for both --steps= and --steps=bogus (was -ne 0, which masked the exit-1 regression). Red/green verified: 4 assertions fail without the fix, 34/34 pass with it.

- ✅ [ONEUP-0014] **Name the duplicate repository in the pre-flight warning.**
  The engine already computes the duplicate URL(s) ($dupe) but the @@REPO@@ marker only carries a generic "duplicate" flag, so the GUI banner can't name the culprit and "Show details" merely expands the full run log (the URL is printed at the top, during pre-flight, and scrolled off). Pass the URL(s) through the marker (@@REPO@@|warn|duplicate|<urls>) and show them in the banner with the removerepo hint.
  **Layman:** When OneUp warns about a duplicate repo, it should say which one — right now "Show details" just shows the log and you can't tell what to fix.
  Kind: enhancement.
  Source: user-report-2026-07-21 (screenshot: generic warning, Show details unhelpful).
  Resolved (2026-07-21): engine flattens the computed duplicate URL(s) and passes them through the marker (@@REPO@@|warn|duplicate|<space-joined urls>); the GUI banner now reads "Duplicate repository URL(s): <url> — remove the extra with 'sudo zypper removerepo <alias>'." instead of a generic message. Tests: engine asserts the marker carries the URL; GUI asserts the banner names the URL + the removerepo hint. Engine 43→44, GUI 29→31.

- ✅ [ONEUP-0015] **Fix a duplicate repository from the app, not just name it.**
  Engine identifies, per duplicated URL, the redundant alias(es) to remove (keep one, prefer an enabled copy) and passes them in the marker (@@REPO@@|warn|duplicate|<urls>|<removable-aliases>). GUI turns the warn-banner button into 'Fix it…' for a repo duplicate: a confirm dialog naming the exact aliases, then pkexec zypper removerepo (alias-validated, mirrors the rollback/service guards). Reversible + confirmed.
  **Layman:** The duplicate-repo warning should have a button that removes the redundant repo for you (after confirming), instead of only telling you to run a command.
  Kind: feature.
  Source: user-request-2026-07-21 (follow-up to ONEUP-0014: 'tell me how to resolve it too or fix it via the app').
  Resolved (2026-07-21): scope grew (user follow-up) from a one-off "fix duplicate" button to a full Repositories manager. Added read_repos()/_parse_repos() (read-only `zypper lr -u`, LC_ALL=C) and RepoManagerDialog — a scrollable list with reused ToggleSwitch on/off per repo, ⚠ + a Remove action only on repos whose URL duplicates another's. Changes apply together via one validated pkexec call (_build_apply_command: modifyrepo --disable/--enable + removerepo; returns [] for no-change, None for an unsafe alias so it never reaches the root shell — mirrors the rollback/service-name guards). Reached from a new header "Repositories" button and from the duplicate-repo warning banner (its button becomes "Manage repositories…"). Tests: 14 GUI checks (parse, duplicate flag, apply-command incl. no-change/unsafe cases, banner dispatch). Superseded the narrower ONEUP-0014 "Fix it" idea. GUI 31→43.

- ✅ [ONEUP-0016] **Polish the Repositories manager: wider, remembers size, centered popups, per-repo descriptions.**
  Widened the dialog (min 720, default 780x560) so repo URLs aren't clipped; it now remembers its size across opens (repos_geometry in QSettings, saved in done()). Both the About and Repositories popups open centered over the main window (RepoManagerDialog.showEvent centres over parent; show_about centres the QMessageBox via QTimer + Updater._center_child). Added _repo_purpose(): a plain-English one-liner per repo derived from alias/name/URL patterns (debug/source/non-oss/update/oss/packman/nvidia/chrome/OBS-community/…), shown as a description line in each row. Tests +6 (GUI 43→49).
  **Layman:** Follow-up tweaks to the Repositories popup so it's easier to read and use.
  Kind: ux.
  Source: user-request-2026-07-21 (follow-ups to ONEUP-0015).
