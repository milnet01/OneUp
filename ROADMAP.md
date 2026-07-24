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

- ✅ [ONEUP-0012] **Wire up the fully hands-off OBS rebuild (token + webhook / SCM-CI).**
  Set up OBS's GitHub token + webhook (or .obs/workflows.yml) so a pushed tag triggers a rebuild from the git checkout, removing release.sh's osc step and the manual _service re-upload. One-time OBS account setup (token + repo webhook); needs building from git rather than an uploaded _service. See packaging/obs/README.md 'fully hands-off' note.
  **Layman:** Make OBS rebuild the package on its own whenever a new version tag is pushed — no local osc, no re-upload.
  Kind: enhancement.
  Source: suggestion 2026-07-21.
  Progress (2026-07-21): scaffolded + documented, awaiting user OBS activation. Added .obs/workflows.yml (a rebuild_on_tag workflow firing trigger_services on tag_push; inert until wired) and a concrete token+webhook setup section in packaging/obs/README.md. Honest framing recorded: release.sh ALREADY retriggers the OBS rebuild via osc, so the webhook only adds value for a bare `git push --tags` that bypasses release.sh — and even then, trigger_services rebuilds whatever _service pins as <revision>, so true hands-off for arbitrary tags needs converting the OBS package to build directly from the git ref (SCM-linked model), a bigger one-time restructure. Left planned: needs the user's OBS workflow token + GitHub webhook + a verification tag push (can't be tested from here).
  Resolved (2026-07-21): user activated it. OBS workflow token created (home:milnet, id 11691, type workflow, path .obs/workflows.yml) with an SCM Token = a GitHub public_repo PAT; GitHub webhook added (payload = the token trigger URL https://build.opensuse.org/trigger/workflow?id=11691, secret = the OBS token secret, event = push) and its ping delivered green. Corrected packaging/obs/README.md to the verified flow — my earlier draft guessed at the SCM-Token-is-a-GitHub-PAT step and the trigger-URL/secret mechanics. Standing caveat unchanged: trigger_services rebuilds whatever _service pins as <revision>, so NEW versions still go via release.sh (which updates the revision + rebuilds); the webhook is a redundant poke for the common path and a handy manual rebuild trigger.

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

- ✅ [ONEUP-0017] **Preview what will change (package list + download size) before running.**
  Extend the read-only Check pass to parse `zypper dup --dry-run` (and flatpak/fwupd equivalents) and surface the package list, version deltas and total download size in an expandable panel per task. Reuses the existing CHECK marker plumbing.
  **Layman:** Before you hit Update, see the actual packages that will change (old to new version) and the total download size, not just a count.
  Kind: feature.
  Source: user-request-2026-07-21.
  Resolved (2026-07-21): --check now emits @@CHECK_ITEM@@ per changed package (name, old→new version), shown in an expandable per-task panel; system row has an on-demand "Show download size" link that runs the new --size=system engine mode (authenticates, parses zypper dup --dry-run). Rootless list stays password-free.

- ✅ [ONEUP-0018] **Add a system-tray icon that goes 'ready' when updates are waiting.**
  QSystemTrayIcon reflecting the weekly background check result; right-click menu to run now / open the window / dismiss. Tolerate desktops without a tray.
  **Layman:** A small icon near the clock that quietly turns amber when updates are waiting, with right-click run/launch, instead of relying on catching a weekly popup.
  Kind: feature.
  Source: user-request-2026-07-21.
  Resolved (2026-07-23): shipped. Optional system-tray icon that turns amber when updates are waiting, with a Check now / Update now / Open OneUp / Quit right-click menu and an opt-in "Start at boot". The tray runs its OWN independent read-only --check every ~6h (silent — no --notify), superseding this bullet's "reflect the weekly check result" gloss and its "dismiss" menu wording. All in updater.py (no engine/marker change); a single _ensure_tray() owns all resident setup (icon, single-instance QLocalServer, check timer, quit-behaviour). Built via a 4-loop cold-eyes spec (docs/specs/ONEUP-0018-system-tray-icon.md), a 7-task subagent-driven TDD plan (docs/plans/ONEUP-0018-system-tray-icon.md) with per-task reviews, and a final whole-branch review whose one Important finding (an unparented QMenu that could be garbage-collected) was fixed. local-CI green: engine 75/0, gui-smoke 120/0.

- ✅ [ONEUP-0019] **Call out kernel and graphics-driver updates by name in the reboot advice.**
  Detect kernel / DKMS / graphics-driver packages in the installed set and pass a reason string through the REBOOT/INSTALLED marker so the banner can name them.
  **Layman:** When a reboot is advised, say why in plain English - e.g. a new kernel and your NVIDIA driver were installed - instead of a generic 'reboot advised'.
  Kind: enhancement.
  Source: user-request-2026-07-21.
  Resolved (2026-07-24): engine scans the system transaction log for kernel (kernel-default/preempt/…), graphics-driver (NVIDIA, Mesa, xf86-video-, libvulkan/libdrm) and DKMS/KMP module names and builds a plain-English reason phrase (reboot_reason_from_log). It rides through a new optional third field on the marker — @@REBOOT@@|yes|<reason> — with the no-reboot marker left byte-identical (@@REBOOT@@|no). The GUI names it in the reboot banner (NVIDIA casing preserved), falling back to the generic wording when absent. Reason is read while $SYS_LOG still exists (it is rm'd before the reboot check) and only ever NAMES a reboot the engine already earned — never invents one. Firmware-triggered reboots now surface their existing "firmware was updated" reason for free. Marker doc updated in CLAUDE.md; engine + GUI-smoke regression tests added (108 + 145 green), incl. an honesty guard that a reason-less 102 reboot does NOT falsely name a kernel.

- 📋 [ONEUP-0020] **Let the user pick which snapshot to roll back to, not just the last one.**
  Enumerate recent Snapper snapshots (snapper list) in a dialog; roll back to the chosen one. Builds on the existing rollback path.
  **Layman:** List recent restore points with dates so you can undo a problem that started two updates ago, not only the most recent run.
  Kind: feature.
  Source: user-request-2026-07-21.

- 📋 [ONEUP-0021] **Warn when Btrfs snapshots are eating the disk, and offer to thin them.**
  Measure /.snapshots usage in the pre-flight/DISK check; when high, surface a HINT and offer a guarded snapper cleanup. Extends the existing disk-space warning.
  **Layman:** Snapshots quietly fill the disk on Tumbleweed; warn when they are using a lot of space and offer a one-click cleanup - like the existing low-disk warning.
  Kind: feature.
  Source: user-request-2026-07-21.

- ✅ [ONEUP-0022] **Add an optional unattended (scheduled full-update) mode, off by default.**
  Systemd timer that runs the engine (not just --check) on a schedule, reusing the snapshot/rollback safety. Off by default; opt-in from the GUI alongside the weekly-check toggle.
  **Layman:** A true set-and-forget option: run the whole update on a schedule with the existing snapshot + rollback safety net, for people who never want to think about it.
  Kind: feature.
  Source: user-request-2026-07-21.
  Resolved (2026-07-23): weekly unattended full-update timer (oneup-update.{service,timer}, OnCalendar=weekly, Persistent=true), off by default, gated on ONEUP-0023 passwordless. Engine skips the interactive sudo -v bootstrap when the drop-in is active and notifies with the outcome at the end of a full run; GUI groups the three background toggles (weekly check, passwordless, automatic updates) behind a Settings popup and couples auto-update on/off to passwordless via a single async-settle install gate (timer can never be enabled while passwordless is off). Built subagent-driven from docs/plans/ONEUP-0022-unattended-updates.md; per-task + opus whole-branch review clean. Local CI green (75 engine + 81 GUI). Not yet released (separate bump).

- ✅ [ONEUP-0023] **Add an opt-in "remember my authorization" mode (no password stored).**
  Deliberately does NOT store the sudo password (encrypting a password the app must itself decrypt is obfuscation, not security, and a stored root password breaks OneUp's 'GUI never touches root' design). Instead install a scoped, revocable sudoers drop-in (/etc/sudoers.d/oneup) that lets the user run OneUp's update commands (zypper, snapper, systemctl stop packagekit) without a password. Toggle on = install the drop-in (validated with visudo -c) after one authenticating prompt; toggle off = remove it. This is also the mechanism the unattended-updates mode (ONEUP-0022) needs. Consider session-only vs permanent scoping.
  **Layman:** An opt-in setting so OneUp stops asking for your password every time - the operating system remembers the decision, not the password. Off by default; leave it off and it prompts as it does now. Turn it off to revoke instantly.
  Kind: feature.
  Source: user-request-2026-07-21.
  Design decided (2026-07-21): mechanism = scoped, revocable sudoers drop-in (NOT password storage, NOT keyring). Duration = "Always" only — dropped the session-only sub-option (sudoers is persistent). Single opt-in toggle: on = install /etc/sudoers.d/oneup (validate with `visudo -c` before moving into place), off = delete it (instant revoke). Present with an explicit warning that this ≈ passwordless root for OneUp's update commands (zypper can run arbitrary root code; env can launch anything) — scoped to the union of binaries only: zypper, snapper, `systemctl stop packagekit`, flatpak, and `env LC_ALL=C zypper` (the engine forces the locale via `sudo env`, so the rule must cover that exact form). Never store the password. Build steps: engine gains --grant-auth / --revoke-auth / --auth-status actions (grant needs one authenticating prompt); GUI Settings toggle drives them + shows the warning; tests assert the drop-in content is visudo-valid and revoke removes it. Enables unattended updates (ONEUP-0022).
  Resolved (2026-07-21): implemented as designed. Engine gained --grant-auth / --revoke-auth / --auth-status (update_system.sh): grant builds a scoped sudoers drop-in from command -v real paths (zypper any-args, snapper, flatpak, `systemctl stop packagekit`, and the `env LC_ALL=C zypper *` wrapper the engine uses), validates it with `visudo -cf` before install -m0440, and stores NO password; revoke deletes it (instant); status probes with `sudo -k -n zypper --version` (cache-immune) and emits @@AUTH@@|on/off. AUTH_FILE overridable via $ONEUP_AUTH_FILE for hermetic tests. GUI: a "Passwordless" header toggle (updater.py) that shows an explicit ≈passwordless-root warning before granting, drives the engine actions, and re-probes real state on finish (a cancelled prompt reverts the switch). Window min-width raised 560→720 so the 5th header control doesn't crowd the title. Tests: 60 engine (grant is visudo-valid incl. real-visudo check, revoke removes the file, status can't be fooled by a cached credential) + 54 GUI smoke. Marker contract, CLAUDE.md, CHANGELOG [Unreleased] updated. local-CI green.

- ✅ [ONEUP-0024] **Cap or roll the tray-check log files so a long resident session doesn't accumulate them.**
  Each _tray_check() writes LOG_DIR/<stamp>.traycheck.log; a resident tray runs ~4/day indefinitely, so the files accumulate. Flagged Minor (acceptable-for-merge) by the ONEUP-0018 final whole-branch review. Fix: point the tray check at a single rolling traycheck.log (overwrite each run) — its output is silent/not user-facing, so no history is lost.
  **Layman:** When the tray runs for weeks, each background check leaves a small log file; reuse one rolling log instead of piling up new ones.
  Kind: enhancement.
  Source: final-review-2026-07-23 ONEUP-0018.
  Resolved (2026-07-24): _tray_check now writes one rolling LOG_DIR/traycheck.log via the new _traycheck_log() helper, which mkdir's and truncates the file each run. The engine's `tee -a` resumes from the truncated file, so reusing the fixed name still overwrites (silent output, no history lost) — a resident tray no longer piles up a timestamped file ~4x/day. Regression test added in tests/gui-smoke.py (4b): asserts one fixed filename and truncation-each-run. local-CI green (engine 108, gui-smoke 147).

- ✅ [ONEUP-0025] **Survive a single broken software source instead of failing the whole update.**
  Context-aware: a manual run offers "Skip <source> & update the rest" in the warn banner; an unattended run (weekly/tray) auto-skips the culprit, finishes, and notifies. Never weakens the signature check — the source is temporarily disabled via zypper's on/off switch and always re-enabled (trap-restored). Safety cap: refuse to silently skip more than a couple of sources at once. New engine flag --skip-repo=<alias> (repeatable) + an unattended auto-skip mode + markers @@REPO_SKIPPED@@|alias|reason and @@REMEDY@@|skip-repo|alias. Keeps the existing import-keys remedy for a genuinely expired key. Alias validated before it reaches the privileged zypper modifyrepo call.
  **Layman:** When one repository (e.g. Google Chrome) serves a bad signature or is unreachable, OneUp now sets just that source aside, updates everything else, and retries it next time — instead of the whole update failing.
  Kind: feature.
  Source: user-request-2026-07-23.
  Spec written (docs/specs/ONEUP-0025-repo-resilience.md) and cold-eyes converged in 2 loops (loop 1: 3 HIGH / 2 MED / 3 LOW fixed — alias-regex divergence, false _launch call-site, lr-parse claim, reason-enum derivation, REPO_SKIPPED routing; loop 2: polish only, all citations verified accurate). Ready to implement on branch anthony/ONEUP-0025-repo-resilience.
  Resolved (2026-07-23): shipped via subagent-driven development (6 TDD tasks) on branch anthony/ONEUP-0025-repo-resilience, merged to main (ff). Engine: --skip-repo=<alias> (disable→full dup→trap-restore, alias-validated fail-closed), --auto-skip-repos (probe failing repos individually, classify reason, skip up to MAX_SKIP_REPOS=2, retry on the healthy set), markers @@REPO_SKIPPED@@|alias|reason + @@REMEDY@@|skip-repo|alias; never --no-gpg-checks; happy path unchanged. GUI: _launch skip_repos, _headless_update passes --auto-skip-repos (unattended auto-skip), a "Skip <source> & update the rest" banner action (+ genuine 2nd button when an expired-key import remedy is also armed). Spec cold-eyes converged (2 loops). Whole-branch opus review caught 2 Important engine↔GUI integration bugs — metadata-source failure showed no skip banner (banner gated on HINT); multiple broken repos overwrote a scalar remedy — both fixed (commit 536343c) with regression tests. Final: engine 99/0, gui-smoke 142/0, local-CI green. CHANGELOG [Unreleased] carries the entry; no version bump (batched into the next release).

- ✅ [ONEUP-0026] **Adopt a popup/dialog standard: theme-matched and always centered on the app.**
  Write a short standard (docs/standards/) covering OneUp dialogs: (1) inherit the app palette so light/dark matches the main window; (2) always open centered over the parent window via the existing _center_child / showEvent-centring helper. Then bring the outlier into line: the signing-key import confirmation (a QMessageBox) currently opens at the compositor's default spot, not centered — route it through the same centring helper the About/Repositories popups use. Audit all dialogs for both properties. Reuses ONEUP-0016's _center_child machinery; no new mechanism.
  **Layman:** Make every popup window look and behave consistently — matching the app's light/dark theme and always opening centered over the main window. Right now the About and Repositories popups center correctly, but the signing-key warning doesn't.
  Kind: doc.
  Source: user-request-2026-07-23.
  Resolved (2026-07-24): Wrote docs/standards/dialogs.md codifying the two popup properties (theme-matched via the app-wide QSS inherited by all children; centered via the showEvent override for QDialog subclasses and QTimer.singleShot(0, _center_child) for hand-built QMessageBoxes). Audited all dialogs: RepoManagerDialog/SettingsDialog centre via showEvent; show_about already centred. Fixed the two outliers that built a QMessageBox and exec'd it without centring — _confirm_key_import (the named signing-key box) and _confirm_passwordless — by routing both through _center_child exactly as show_about does. Theme-matching needed no work: apply_theme() sets the stylesheet app-wide and re-applies on colorSchemeChanged, so every child popup inherits it. Static convenience QMessageBox.* calls left as-is (parent-relative default, documented as acceptable for transient notices). local-CI green (108 engine + 165 GUI smoke tests).

- 📋 [ONEUP-0027] **Offer additional themes beyond following the system light/dark scheme.**
  Today OneUp follows the desktop light/dark palette and switches live. This item adds a small set of selectable themes (a Settings picker) layered on that. Should coordinate with ONEUP-0026 (dialog standard) so any new theme applies consistently across the main window AND all popups/dialogs. Design open: how many themes, whether "Follow system" stays the default, and where the picker lives.
  **Layman:** Let people choose from a few built-in colour themes for OneUp, instead of only matching the desktop's light or dark setting.
  Kind: feature.
  Source: user-request-2026-07-23.

- 📋 [ONEUP-0028] **Make OneUp usable for blind, partially-sighted, and colour-blind users.**
  Cover the three groups: (1) blind — full screen-reader (Orca/AT-SPI) support: accessible names/roles on every control, the live log and progress announced, focus order sane, no unlabelled icon-only buttons; (2) partially sighted — scalable/large text, honour the desktop font scale, a high-contrast option, keyboard operability throughout; (3) colour-blind — never signal state by colour alone (the amber tray icon, red/green step badges) — pair every colour cue with text/shape/icon. Coordinates with ONEUP-0026 (dialog standard) and ONEUP-0027 (themes: any theme must keep WCAG-AA contrast). Likely warrants its own spec + an audit pass with Orca.
  **Layman:** Design OneUp so people who can't see well — or at all — can still use it: screen-reader support, large/scalable text and high-contrast options, and never relying on colour alone to convey status.
  Kind: accessibility.
  Source: user-request-2026-07-23.

- ✅ [ONEUP-0029] **Report how much disk space the cache clean actually freed.**
  Measure /var/cache/zypp (du) before and after `zypper clean --all` in update_system.sh (~line 813) and print/emit the delta. The cache step is the only task whose benefit the user can't currently see. Small, no risk. Natural lead-in to ONEUP-0021 (snapshot thinning).
  **Layman:** After clearing the package cache, show 'Reclaimed 1.4 GiB' so the least-visible step has a visible payoff.
  Kind: enhancement.
  Source: in-session-2026-07-23.
  Resolved (2026-07-24): engine measures /var/cache/zypp before/after `zypper clean --all` and emits @@FREED@@|cache|<human>; GUI shows it as the cache row's "Reclaimed <size>" badge. New FREED marker documented in CLAUDE.md; engine + GUI-smoke tests cover the reclaim path and the already-empty (no-marker) case.

- ✅ [ONEUP-0030] **Show a 'last updated N days ago' nudge on launch.**
  Derive from the existing run history in ~/.local/state/oneup/history.json. Surface 'Last updated N days ago' on the dashboard; amber-tint past ~2 weeks. Ties into the existing tray icon so a resident session nudges without a popup.
  **Layman:** On opening OneUp, remind the user how long since their last update, and gently flag it once it's been a couple of weeks.
  Kind: feature.
  Source: in-session-2026-07-23.
  Resolved (2026-07-24): refresh_last_run() now appends a relative day-count (today / yesterday / N days ago) to the existing 'Last run: …' line, and ambers the whole line via a dynamic stale property + QLabel#LastRun[stale="true"] QSS rule once a run is STALE_AFTER_DAYS (14) old. New per-theme `amber` palette token (brighter on dark #f5a623, darker on light #b5730a for 12px legibility). Counts any real run (OK or errors); --check never writes history so background checks don't reset the clock. Tray left unchanged per user choice (dashboard-line-only nudge). 8 new gui-smoke checks (today/yesterday/N-days/threshold-boundary/never). local-CI green: engine 108/0, GUI smoke 165/0.

- ✅ [ONEUP-0031] **Add a one-click 'copy diagnostics for a bug report' button.**
  Bundle the latest run log, OneUp version, openSUSE version, and enabled toggles onto the clipboard. Makes GitHub issues actionable for non-technical users without pointing them at ~/.local/state/oneup/logs.
  **Layman:** One button that copies the run log plus version info to the clipboard, so filing a bug report doesn't mean hunting through hidden folders.
  Kind: feature.
  Source: in-session-2026-07-23.
  Resolved (2026-07-24): Added a 'Copy diagnostics' button to the Settings dialog (updater.py). It bundles the OneUp version, openSUSE PRETTY_NAME, the enabled/disabled tasks, and the most-recent real run log onto the clipboard, with a light scrub (home path -> ~, hostname -> <host>) so a public paste doesn't leak the username/machine. Oversized logs are trimmed to their last 200 KB (errors sit at the tail). GUI-only, no engine changes; /etc/os-release read directly. Logic split into pure helpers build_diagnostics / _latest_run_log with 10 new gui-smoke.py regression checks (157 pass). local-CI green.

- 📋 [ONEUP-0032] **Wrap UI strings for translation (i18n groundwork).**
  Wrap user-facing strings in updater.py with self.tr() and keep a Qt .ts/.qm workflow ready. openSUSE has a large European base. Doing it before the string count grows keeps the door open even if no second locale ships initially.
  **Layman:** Prepare the app so its text can be translated into other languages later (German, etc.) — cheap to do now, expensive once the wording grows.
  Kind: enhancement.
  Source: in-session-2026-07-23.

- ✅ [ONEUP-0033] **bump.py: advance the CHANGELOG [Unreleased] compare-link base to the new tag.**
  bump.py rewrites the six version sites and adds a new `[x.y.z]: .../releases/tag/vX.Y.Z` reference link, but leaves the `[Unreleased]: .../compare/vPREV...HEAD` link pointing at the PREVIOUS tag. After releasing 1.2.0 the link still reads `compare/v1.1.0...HEAD` (CHANGELOG.md:207) — it should read `compare/v1.2.0...HEAD`. Fix: in bump.py, when moving `## [Unreleased]` to `## [X.Y.Z]`, also rewrite the `[Unreleased]:` compare base from the old tag to `vX.Y.Z`. Cosmetic (the link 404s on the stale range only until the next commit), pre-existing since at least 1.1.0. Add/adjust a bump.py test to assert the Unreleased compare base advances. No version-lockstep impact (local-CI's lockstep gate doesn't check this link).
  **Layman:** When we cut a release, the changelog's 'Unreleased' comparison link keeps pointing at the previous version instead of the one just released, so it shows the wrong range. Fix the release tool to update it automatically.
  Kind: fix.
  Source: in-session-2026-07-24.
  Resolved (2026-07-24): bump.py step 6 now runs a third CHANGELOG edit that rewrites the `[Unreleased]: .../compare/vPREV...HEAD` base to `vX.Y.Z` (regex `(\[Unreleased\]: \S+/compare/)v\d+\.\d+\.\d+(\.\.\.HEAD)`). Also fixed the already-stale committed footer (v1.1.0 → v1.2.0). Added tests/bump-test.py — a stdlib-only functional test that runs a real bump in a throwaway repo copy (5 real version files + a synthetic CHANGELOG) and asserts the compare base advances; wired into local-CI.sh and .github/workflows/release.yml. Reproduced the bug first (test failed on the compare-base assertion pre-fix), then fixed. Full local-CI green (108 engine + 165 GUI + 5 bump).
