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

- 📋 [ONEUP-0004] **Refresh the dependencies; chiefly bump CI's Python to 3.14.**
  release.yml pins python-version 3.13 (not 3.14) pending confirmation that PySide6 publishes 3.14 wheels — see docs/standards/dependencies.md ledger. When newer wheels exist, bump and delete the ledger row.
  **Layman:** We're one Python version behind on purpose until the GUI toolkit supports the newest one.
  Kind: chore.
  Source: dependency-standard 2026-07-21.
  Progress (2026-07-26): the premise was checked and is wrong. PySide6
  ships STABLE-ABI wheels (pyside6-6.11.1-cp310-abi3-manylinux_2_34_x86_64.whl,
  requires_python <3.15,>=3.10), so there is no per-version wheel to wait
  for — cp310-abi3 installs on 3.14 today, and manylinux_2_34 is satisfied
  by the ubuntu-22.04 runner (glibc 2.35). Nothing is broken and nothing
  is blocking. The ledger row in docs/standards/dependencies.md has been
  removed (a suspicion is a backlog item, not a documented breakage); this
  bullet is now the sole tracker. The actual one-line bump of
  release.yml's python-version 3.13 -> 3.14 is deferred to the 2.0
  dependency refresh on the v2 branch, because main is frozen at 1.4.0 and
  takes only qualifying bug fixes.

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

- ✅ [ONEUP-0020] **Let the user pick which snapshot to roll back to, not just the last one.**
  Enumerate recent Snapper snapshots (snapper list) in a dialog; roll back to the chosen one. Builds on the existing rollback path.
  **Layman:** List recent restore points with dates so you can undo a problem that started two updates ago, not only the most recent run.
  Kind: feature.
  Source: user-request-2026-07-21.
  Resolved (2026-07-24): engine emits up to the 12 newest restore points as @@SNAPSHOT_ITEM@@|id|date|description (machine-readable CSV `snapper list`, skipping snapshot 0), alongside the existing pre-update @@SNAPSHOT@@. The GUI captures them into Updater._snapshots and Updater.rollback now opens RollbackDialog — a QListWidget picker (newest-first, pre-update snapshot pre-selected) — then confirms and runs `pkexec snapper rollback <chosen> && systemctl reboot`. The chosen id is re-validated as a bare number before it reaches the root shell. Falls back to the single pre-update snapshot when no items were enumerated (older engine / listing failed). Tests: run-tests.sh asserts the SNAPSHOT_ITEM emission + snapshot-0 skip; gui-smoke.py asserts capture, non-numeric-id drop, newest-first ordering, pre-select, and selected_id. Marker documented in update_system.sh header + CLAUDE.md. local-CI green (117 engine / 175 gui).

- ✅ [ONEUP-0021] **Warn when Btrfs snapshots are eating the disk, and offer to thin them.**
  Measure /.snapshots usage in the pre-flight/DISK check; when high, surface a HINT and offer a guarded snapper cleanup. Extends the existing disk-space warning.
  **Layman:** Snapshots quietly fill the disk on Tumbleweed; warn when they are using a lot of space and offer a one-click cleanup - like the existing low-disk warning.
  Kind: feature.
  Source: user-request-2026-07-21.
  Resolved (2026-07-24): engine pre-flight now counts Btrfs snapshots (root, after the low-disk check) and emits @@SNAPSHOTS@@|warn|count once >= SNAP_WARN_COUNT (25). Count is the honest signal — CoW extent-sharing makes a byte figure overcount and per-snapshot quotas are usually off. New --thin-snapshots engine action runs snapper's own guarded cleanup (number/timeline — retention-policy only, never a hand-pick), reports @@SNAPSHOTS@@|thinned|removed via before/after count. GUI: warn banner retargets its button to "Thin snapshots…", which after a confirmation runs the engine as a dedicated privileged process (_thin_snapshots/_on_thin_finished), guarded against firing mid-run (_run_active). Tests: 5 new engine cases (warn >=25, no-warn below threshold, cleanup invoked, thinned count, zero-removed no-false-claim) + 5 gui-smoke assertions. local-CI green (engine 114, gui-smoke 170, lint/validate/lockstep).

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
  Resolved (2026-07-24): Wrote docs/standards/dialogs.md (merged into
  docs/standards/ui-and-accessibility.md §6 on 2026-07-26, ONEUP-0057) codifying the two popup properties (theme-matched via the app-wide QSS inherited by all children; centered via the showEvent override for QDialog subclasses and QTimer.singleShot(0, _center_child) for hand-built QMessageBoxes). Audited all dialogs: RepoManagerDialog/SettingsDialog centre via showEvent; show_about already centred. Fixed the two outliers that built a QMessageBox and exec'd it without centring — _confirm_key_import (the named signing-key box) and _confirm_passwordless — by routing both through _center_child exactly as show_about does. Theme-matching needed no work: apply_theme() sets the stylesheet app-wide and re-applies on colorSchemeChanged, so every child popup inherits it. Static convenience QMessageBox.* calls left as-is (parent-relative default, documented as acceptable for transient notices). local-CI green (108 engine + 165 GUI smoke tests).

- 📋 [ONEUP-0027] **Offer additional themes beyond following the system light/dark scheme.**
  Today OneUp follows the desktop light/dark palette and switches live. This item adds a small set of selectable themes (a Settings picker) layered on that. Should coordinate with ONEUP-0026 (dialog standard) so any new theme applies consistently across the main window AND all popups/dialogs. Design open: how many themes, whether "Follow system" stays the default, and where the picker lives.
  **Layman:** Let people choose from a few built-in colour themes for OneUp, instead of only matching the desktop's light or dark setting.
  Kind: feature.
  Source: user-request-2026-07-23.
  Confirmed by the user (2026-07-26): themes are REQUIRED for 2.0, not
  optional — the item's place in the release is settled and it appears in
  docs/design/oneup-2.0.md section 1. The three design questions in the
  bullet above (how many themes, whether "Follow system" stays the
  default, where the picker lives) are still open and are asked together
  when the spec is written (ONEUP-0057 plan, Task 15). Every theme must
  satisfy the contrast and colour-never-alone rules from ONEUP-0028; a
  theme that cannot is not shipped.
  Measured (2026-07-26, gotcha sweep): the theme machinery does not reach
  every colour. 116 hex literals live in updater.py; most sit inside the
  _QSS Template (254-394, 451) and so follow build_theme(), but ten do
  not and a new theme cannot touch them: GREEN/RED (222-223),
  TRAY_ATTENTION_COLOR (141), and seven QColor() calls inside paintEvent
  overrides — the ToggleSwitch painter (691, 719, 722, 725) and the tray
  icon painter (2072, 2078, 2090). Painted widgets bypass QSS entirely,
  so the switch and tray badge would keep their current colours under
  every new theme. The spec (ONEUP-0057 plan, Task 15) must therefore
  define theme tokens the painters read, not only QSS variables, and the
  per-theme WCAG-AA contrast check must cover the painted surfaces too —
  they are exactly the ones carrying state meaning.
  Spec written (2026-07-27): docs/specs/ONEUP-0027-themes.md, Status
  Reviewed after four cold-eyes loops (9 findings, then 9, 3, 1). The three
  open design questions are answered by the user: eight themes to start,
  "Follow system" stays the default, the picker lives in Settings. A named
  theme is one fixed palette, so choosing one is choosing not to follow the
  desktop; the two shipped palettes are two of the eight.
  Measured while writing the check ui-and-accessibility.md section 7 asks
  this item for: nine pairs fail today, not one. The worst is the switch's
  white state shape at 2.10:1 against its own green track - that shape is
  the colour-blind cue, so the weakest thing on screen is the one carrying
  meaning. Also light lastrun 3.07:1, light amber 3.87:1, and the ghost
  button's border at 1.62:1.
  The gotcha-sweep note above undercounted: ten literals sit in the two
  painters, and THIRTY MORE inside the _QSS template itself, twelve
  distinct, including #4aa3ff written out in eight places. Substitution
  does not touch them, so a theme could set the accent and leave the Run
  button azure. Every one becomes a token.
  Two ordering facts the spec depends on: ONEUP-0034 creates
  oneup/gui/theme.py, and ONEUP-0076 lands BEFORE this item, so the focus
  measurement is inherited rather than built here.

- ✅ [ONEUP-0028] **Make OneUp usable for blind, partially-sighted, and colour-blind users.**
  Cover the three groups: (1) blind — full screen-reader (Orca/AT-SPI) support: accessible names/roles on every control, the live log and progress announced, focus order sane, no unlabelled icon-only buttons; (2) partially sighted — scalable/large text, honour the desktop font scale, a high-contrast option, keyboard operability throughout; (3) colour-blind — never signal state by colour alone (the amber tray icon, red/green step badges) — pair every colour cue with text/shape/icon. Coordinates with ONEUP-0026 (dialog standard) and ONEUP-0027 (themes: any theme must keep WCAG-AA contrast). Likely warrants its own spec + an audit pass with Orca.
  **Layman:** Design OneUp so people who can't see well — or at all — can still use it: screen-reader support, large/scalable text and high-contrast options, and never relying on colour alone to convey status.
  Kind: accessibility.
  Source: user-request-2026-07-23.
  Progress (2026-07-25): spec drafted at docs/specs/ONEUP-0028-accessibility.md and
  run through /cold-eyes. Loop 1 surfaced 8 HIGH / 10 MEDIUM / 9 LOW (28 verified,
  1 dismissed); all verified findings fixed in the spec. Notable: the HC overlay
  must restate every pseudo-state selector (CSS2 specificity — a bare rule cannot
  beat #RunBtn:hover), the font-scale base needs a clamp (Qt's -1 sentinel is
  truthy, so `or 10.0` misses it), and two draft invariants could not fail against
  today's code. Verified along the way that a checkable QAbstractButton already
  maps to Role.CheckBox with checked state, so no custom accessible interface is
  needed for the roadmap's "roles" requirement.
  Resolved (2026-07-25): implemented per docs/specs/ONEUP-0028-accessibility.md
  (cold-eyes converged, 2 loops). Screen reader: accessible names on every focusable
  control (task switches, disclosure arrows, detail lists, progress bar, log,
  banners, repo switches, rollback list) — a nameless focusable widget now FAILS
  gui-smoke; announcements via one _announce helper (step begin/end, warnings, final
  summary) using Qt 6.8's QAccessibleAnnouncementEvent with an Alert fallback for
  older PySide6. Roles needed no work: a checkable QAbstractButton already maps to
  an accessible CheckBox carrying the checked state. Low vision: the twelve
  hard-coded px font sizes are gone, derived from the desktop's default point size
  times a new Settings "Text size" control (Normal/Large/Larger); badge padding and
  progress-bar height scale with it; a "High contrast" option appends an overlay that
  restates every :hover/:checked/[attr] rule (Qt follows CSS2 specificity, so a bare
  rule cannot beat #RunBtn:hover). Colour-blind: bar/circle shape on the switches, a
  "!" glyph in the tray badge, "⚠ overdue" in words. Tab order follows visual order.
  36 new GUI assertions (211 total). DEVIATION from the spec: no focus ring — the
  user rejected focus borders/outlines on sight (an outline renders as a square
  around the rounded buttons because Qt ignores outline-radius), so focus reuses the
  hover look instead. That trades away WCAG 2.4.7's visible-focus requirement for
  sighted keyboard-only users; the roadmap's Orca audit pass remains the open
  follow-up, and a subtler cue could revisit it.

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
  Scope settled by the user (2026-07-26), now a 2.0 item — see
  docs/design/oneup-2.0.md section 5.1. Three decisions: (1) 2.0 ships the
  GROUNDWORK ONLY, English alone; additional languages arrive after 2.0 is
  released, because wrapping strings touches every file that shows text
  while translating them touches no code at all. (2) RIGHT-TO-LEFT
  languages (Hebrew, Arabic) are in scope and land with the groundwork —
  a layout built the wrong way has to be rebuilt, not translated.
  (3) Gate G10 tests the machinery rather than a translation: the GUI
  suite must pass with the layout direction forced RTL.
  Measured at ff4f4a7, the starting position is good: 0 hard-coded
  AlignLeft/AlignRight, 0 existing RTL handling to unpick, and of the
  directional QSS properties only one — #LinkBtn's text-align: left
  (corrected 2026-07-27, cold-eyes batch 2; the earlier "0 directional
  QSS properties" counted only margin/padding/border). So Qt's automatic
  layout mirroring does most of the work.
  The one exception is custom painting, which Qt cannot mirror: the
  toggle's paintEvent (updater.py:699) computes its knob position from
  the left edge (line 712) and must apply the direction itself; its
  the painted state shape is NOT symmetric either — `_paint_state_shape` picks its edge from the state (checked measures from the left, unchecked from `self.width()`), so there are two handed sites in `ToggleSwitch`, not one, and they need different fixes (corrected 2026-07-27, ONEUP-0032 spec review; `docs/standards/ui-and-accessibility.md` §8.3). Also
  10 string-concatenation sites to convert to whole sentences with named
  placeholders — a glued sentence cannot be reordered by a translator and
  renders unpredictably in RTL.
  Spec written and reviewed (2026-08-03): docs/specs/ONEUP-0032-i18n.md,
  Status Reviewed. Seven cold-eyes loops. It was SPLIT at loop 5: the item held
  two contracts, and every finding in loops 4 and 5 sat on one side of a clean
  seam, so the engine-to-window payload conversion left for ONEUP-0072 and this
  item kept the catalogue machinery and right-to-left. Loop 7 reviewed the split
  document in its own right (20 verified, 2 dismissed) and most of what it found
  was the split's own unswept blast radius.

  Ordering settled by the user the same day: this item lands AFTER ONEUP-0072
  and stays last in 2.0, which is where docs/design/oneup-2.0.md section 5.2 had
  always put it. The dependency runs one way — ONEUP-0072 builds the sentence
  tables and puts sentence-rendering on the two headless paths; this item then
  marks those tables and gives those paths the QCoreApplication they need to
  render a translated one. No change to its section 4.1 or 4.2 was needed; both
  were already written for this order.

  Scope confirmed with the user: 2.0 ships the machinery and English only. No
  second-language catalogue is written, reviewed or shipped in 2.0 — that is a
  data file contributed afterwards, not a project. Right-to-left IS in 2.0,
  because a layout built the wrong way has to be rebuilt rather than translated.

- ✅ [ONEUP-0033] **bump.py: advance the CHANGELOG [Unreleased] compare-link base to the new tag.**
  bump.py rewrites the six version sites and adds a new `[x.y.z]: .../releases/tag/vX.Y.Z` reference link, but leaves the `[Unreleased]: .../compare/vPREV...HEAD` link pointing at the PREVIOUS tag. After releasing 1.2.0 the link still reads `compare/v1.1.0...HEAD` (CHANGELOG.md:207) — it should read `compare/v1.2.0...HEAD`. Fix: in bump.py, when moving `## [Unreleased]` to `## [X.Y.Z]`, also rewrite the `[Unreleased]:` compare base from the old tag to `vX.Y.Z`. Cosmetic (the link 404s on the stale range only until the next commit), pre-existing since at least 1.1.0. Add/adjust a bump.py test to assert the Unreleased compare base advances. No version-lockstep impact (local-CI's lockstep gate doesn't check this link).
  **Layman:** When we cut a release, the changelog's 'Unreleased' comparison link keeps pointing at the previous version instead of the one just released, so it shows the wrong range. Fix the release tool to update it automatically.
  Kind: fix.
  Source: in-session-2026-07-24.
  Resolved (2026-07-24): bump.py step 6 now runs a third CHANGELOG edit that rewrites the `[Unreleased]: .../compare/vPREV...HEAD` base to `vX.Y.Z` (regex `(\[Unreleased\]: \S+/compare/)v\d+\.\d+\.\d+(\.\.\.HEAD)`). Also fixed the already-stale committed footer (v1.1.0 → v1.2.0). Added tests/bump-test.py — a stdlib-only functional test that runs a real bump in a throwaway repo copy (5 real version files + a synthetic CHANGELOG) and asserts the compare base advances; wired into local-CI.sh and .github/workflows/release.yml. Reproduced the bug first (test failed on the compare-base assertion pre-fix), then fixed. Full local-CI green (108 engine + 165 GUI + 5 bump).

- 📋 [ONEUP-0034] **Break up updater.py — six times the 600-line ceiling — into focused modules.**
  updater.py is a single ~2,150-line module holding the main window, several dialogs (Settings, Repository manager, About), the @@MARKER@@ protocol parser, the QProcess engine-launch plumbing (run/check/size/auth/thin), banner/remedy state, tray + autostart, and pure helpers (diagnostics, os-release, log discovery). Candidate seams, cohesion-first and behaviour-preserving: (a) pull the pure/stateless helpers into a small module; (b) split the dialogs out; (c) consider isolating the marker-parsing + engine-launch layer from the widget layer. Constraints: keep the marker contract and step-key lists intact (they mirror update_system.sh + the tests), keep the privilege split (GUI never root), and keep local-CI green at every step — gui-smoke imports symbols from updater.py, so preserve public names or update the tests in lockstep. Not urgent; do it opportunistically, in small reviewable commits, only where it genuinely aids the six-month-reader test. Source: user-request-2026-07-24.
  **Layman:** The app's main code file has grown very large. Split it into smaller, well-named pieces so it's easier to find and change things, without altering how the app behaves.
  Kind: refactor.
  Source: user-request-2026-07-24.
  Progress (2026-07-25): the figure in the headline is stale — updater.py is
  now 3,680 lines, not ~2,150, so this is overdue rather than optional. Raised
  by the user in the same session as ONEUP-0048/0049, alongside the wider
  question of rewriting the Bash engine in Python; see ONEUP-0052, which
  records why the two are worth keeping separate.
  Measured (2026-07-26, gotcha sweep): two concrete obstacles the bullet
  above does not yet name. (1) tests/gui-smoke.py:62 loads the GUI with
  importlib.util.spec_from_file_location("updater", REPO/"updater.py") —
  a single-FILE loader. It cannot load a package: the moment updater.py
  becomes updater/ with relative imports, the loader fails outright, so
  the split's first commit breaks the whole 283-check GUI suite, not just
  the symbol names. The test harness has to move to a path-based package
  import before any code moves. (2) The GUI's repo parsing depends on a
  locale pin that no test exercises: read_repos passes
  env={**os.environ, "LC_ALL": "C"} (updater.py:988) because
  _parse_repos reads zypper's human table and decides enabled/disabled
  from cols[3][:1].lower() == "y" — on a German desktop "Ja" gives "j"
  and every repository would read as disabled. The engine has a
  non-English locale regression test (tests/run-tests.sh:1360); the GUI
  has none, so dropping that env kwarg while moving code stays green in
  CI and only breaks for non-English users. Add the GUI-side locale check
  before the split starts.
  Spec written (2026-07-27): docs/specs/ONEUP-0034-gui-modules.md, Status
  Reviewed after four cold-eyes loops (11 findings, then 6, 3, 1; none
  resurfaced). It settles the module list, the import direction, what the
  tests reach for, and twelve invariants. Three things the bullet above does
  not say. The harness moves first, in its own commit: gui-smoke.py's loader
  never puts the repo root on sys.path, so it raises ModuleNotFoundError the
  moment the root updater.py imports the package. A test that patches a
  re-exported name silently stops patching, which is how the suite could stay
  green while the window deleted a live run's run.state — so path constants
  are read through their module, never bound by name. And window.py will not
  fit the 600-line ceiling; the spec says so rather than pretending, and
  ONEUP-0064 is where that is attempted. ONEUP-0059 rides along, in one
  commit across both halves.

- ✅ [ONEUP-0035] **Fix "Show download size" always reporting 0 B, and never report a size the dry run didn't earn.**
  Two defects, one symptom. (1) Stale parse: run_size grepped zypper's
  old "Overall download size: 1.3 GiB. Already cached: 0 B." wording.
  Current zypper (1.14.98 / libzypp 17.38.14) prints "Package download
  size:   371.4 MiB" and no longer contains the old strings at all
  (verified absent from /usr/bin/zypper). No match fell through to the
  "nothing to fetch" branch, so a 371.4 MiB upgrade was reported as 0 B.
  The parse now accepts BOTH wordings — Leap may still ship the older
  zypper. The engine test mock encoded the old wording too, which is why
  CI stayed green; a second mock now pins the current wording.
  (2) A FAILED dry run (cancelled password prompt, held package lock,
  network down) was indistinguishable from "nothing to fetch" and was
  also answered as a confident "0 B" — the exact never-claim-what-you-
  didn't-earn class the suite exists to prevent. run_size now checks the
  exit status, treats zypper's informational 100-103 codes as success,
  and on real failure emits @@HINT@@ + returns non-zero so the GUI
  re-arms its "Show download size" link. The GUI also logs that hint
  (it was previously swallowed, making the re-arm look like a dead
  button). Verified end to end against real zypper: @@SIZE@@|system|371.4 MiB.
  **Layman:** The "Show download size" link said "0 B to download" even with 137 updates waiting — it now shows the real figure, and says so plainly when it can't work the size out instead of pretending it is zero.
  Kind: fix.
  Source: user-report-2026-07-25 (screenshot: 137 available, "↓ 0 B to download").
  Follow-up (2026-07-25): the failure path's hint was itself a guess ("busy or
  cancelled"). It now names the real cause from zypper's documented exit codes — 7
  ZYPP_LOCKED (another program holds the package-manager lock), 5 insufficient
  privileges, 6 no repositories — and echoes the last 5 lines of what zypper
  actually said, prefixed "zypper:". Previously `out` was captured into a variable
  and discarded on failure, so the log recorded only "unavailable" with nothing to
  act on. Found because a user hit the new failure path live: the cause was the
  ZYPP lock held by a concurrent diagnostic dry run, which the old hint would have
  mis-attributed to a cancelled password prompt. Tests: 126 passed / 0 failed.

- ✅ [ONEUP-0036] **Export SUDO_ASKPASS so privileged commands can raise the password prompt without a terminal.**
  The engine set ASKPASS but never exported SUDO_ASKPASS, so only the
  explicit `sudo -A` calls (sudo_init, auth_status) could reach the
  graphical helper. Every other privileged call — including run_size's
  `out=$(sudo env LC_ALL=C zypper … --dry-run)` — relied purely on
  sudo_init's cached credential. That credential is not always visible:
  `out=$(…)` runs in a subshell, and with no tty sudo keys its credential
  record on the PARENT PID, which the subshell changes. The GUI runs the
  engine through QProcess, so there is no tty to fall back on either, and
  the call died with "sudo: a terminal is required to read the password".
  Symptom: "Show download size" failed even after ONEUP-0035 fixed the
  wording parse — the improved diagnostics from that fix are what made
  this visible (the log now echoes what zypper/sudo actually said).
  Fix: `export SUDO_ASKPASS="$ASKPASS"` at the top, which makes the
  project's documented convention (privileged commands raise the KDE
  prompt, never block on stdin) true for EVERY sudo in the file rather
  than just the -A ones. Worst case is now one graphical prompt instead
  of a hard failure. Regression test asserts the helper is visible in the
  environment of the privileged command itself, via a sudo mock that
  reports whether SUDO_ASKPASS reached it. Tests: 129 passed / 0 failed.
  **Layman:** When OneUp asked for your password from a step launched by the window (rather than a terminal), it had no way to show the prompt and simply failed. It can now always show the KDE password popup.
  Kind: fix.
  Source: user-report-2026-07-25 (log: "sudo: a terminal is required to read the password").

- ✅ [ONEUP-0037] **Stop the download-size check asking for a password twice, and label every prompt.**
  Root cause: `out=$(sudo env … zypper --dry-run)` ran the privileged
  command in a COMMAND-SUBSTITUTION SUBSHELL. Per sudoers(5)
  `timestamp_type`, a credential cached with no terminal present is keyed
  to the PARENT PROCESS ID — "commands run via sudo with a different
  parent process ID … will be authenticated separately" — and the GUI runs
  the engine through QProcess, so there is no terminal. sudo_init's
  up-front credential was therefore invisible to that call: before
  ONEUP-0036 it failed outright, and after it (askpass exported) it
  prompted a SECOND time. Fix: redirect to a mktemp file and read it back
  with `out=$(<"$tmp")`, keeping sudo in the same shell — and hence the
  same parent pid — as sudo_init, so the one up-front prompt covers it.
  Trust hardening in the same change: `SUDO_PROMPT` is now exported with a
  OneUp-labelled message, because sudo's own default under this distro's
  `targetpw` reads "[sudo] password for root" — an unattributable request
  for the root password, which a user should refuse on principle. A
  shellcheck SC2024 disable documents why `| sudo tee` is the wrong
  "fix" here (it would put sudo back in a subshell).
  **Layman:** Checking the download size asked for your password twice in a row, and the second box was an unlabelled request for the root password — which understandably looks suspicious. Now it asks once, and any prompt says it is OneUp asking and why.
  Kind: fix.
  Source: user-report-2026-07-25 (two prompts back to back; second read "password for root").

- ✅ [ONEUP-0038] **Ask for the password once per run, not once per privileged step.**
  A user reported three password prompts in a row, twice in one session, the
  extra ones in sudo's own bare "password for root" wording. Measured cause:
  with no terminal (the GUI runs the engine through QProcess) sudo keys its
  cached credential to the PARENT PROCESS ID, and bash forks a real subshell
  for `$(cmd | other)`, `$(a; b)`, `$(cmd "$(nested)")` and `< <(cmd | other)`
  — so a sudo inside one authenticates separately. Eleven privileged captures
  were shaped that way; an instrumented full run needed SEVEN prompts. Added a
  `sudo_capture` helper (temp file we own, no subshell) and routed every capture
  through it, including `find_failing_repos`, whose caller read it through a
  process substitution. Regression test models sudo's per-parent-pid credential
  cache and fails if a full run needs more than one prompt.
  **Layman:** OneUp now asks for your password a single time per update run instead of popping the box three or more times.
  Kind: fix.
  Source: user-report-2026-07-25.

- ✅ [ONEUP-0039] **Name the program holding the package lock instead of failing every step through it.**
  A user quit OneUp mid-download; the engine's zypper kept installing in the
  background (by design — killing a transaction half-way can break the package
  database), so the next run printed zypper's own words twice ("System
  management is locked by the application with pid 447150 (zypper)"), took a
  pointless snapshot, and reported two failed steps whose single cause was
  "OneUp is already busy". The engine now reads the holder's pid from the
  world-readable /run/zypp.pid before touching anything, names it in plain
  English, and stops. A stale entry whose pid is gone does not block a run, and
  a Flatpak- or firmware-only run ignores the lock entirely.
  **Layman:** If something else is already installing software, OneUp now says so in one clear sentence and changes nothing, instead of reporting a pile of failures.
  Kind: fix.
  Source: user-report-2026-07-25.

- ✅ [ONEUP-0040] **Show live per-package progress so a long download can't look like a hang.**
  A user watched a working run sit on "Updating system packages…" for minutes
  while zypper fetched 379 MiB, concluded it was stuck, and quit the app — which
  left the transaction running in the background and blocked the next two runs.
  The engine now parses zypper's own counters (`Retrieving: … (12/77)` and
  `( 7/77) Installing:`) plus the uncounted `Preloading:` prefetch and emits a
  new `@@PROGRESS@@|key|done|total|phase` marker; the GUI puts it in the status
  line, the progress-bar caption and the step's badge. A total of 0 means zypper
  gave no denominator, so the GUI shows a running tally rather than inventing
  one. Screen readers hear a phase change, not 141 packages.
  **Layman:** While OneUp downloads and installs, it now says "Downloading 12 of 141 packages" instead of sitting on one line for minutes.
  Kind: feature.
  Source: user-report-2026-07-25.

- ✅ [ONEUP-0041] **Stop the sudo keep-alive outliving a killed run.**
  Two keep-alive loops were found on the reporter's machine still validating
  sudo every 50 seconds forty minutes after the runs that spawned them had been
  killed. `cleanup`'s trap handles the normal exit but cannot run on SIGKILL, so
  the loop now also watches the engine's pid and exits on its own; it carries an
  `oneup-keepalive` tag in $0. Those orphans were also why the anti-orphan test
  was flaky one run in six: it matched every `sleep 50` on the machine, and a
  leaked loop respawns one every 50 seconds. It now diffs the tagged loop shells,
  whose pids are stable, and a new test asserts the pid guard directly.
  **Layman:** An interrupted update no longer leaves a background helper running for hours.
  Kind: fix.
  Source: in-session-2026-07-25.

- ✅ [ONEUP-0042] **Never abandon an update half-way when the app is closed.**
  The engine's stdout is a pipe to the GUI. Quitting killed `tee`, which SIGPIPEd
  the engine on its next line — killing it without running its cleanup trap, so
  the keep-alive leaked and zypper was left orphaned mid-transaction. A
  half-applied rpm transaction can leave programs broken, and the abandoned lock
  blocked the next two runs. The logging redirect now uses `tee -a -p`
  (--output-error=warn-nopipe, probed not assumed) so tee keeps writing the log
  and the engine finishes the job; a PIPE trap is the fallback. The GUI warns
  before quitting mid-run — the safe "Keep OneUp open" is the default button —
  and closing to the tray is left alone, since it isn't a quit. Verified
  falsifiable: without the flag the engine dies after five log lines and never
  reaches @@DONE@@.
  **Layman:** Closing OneUp during an update now warns you first, and the update itself finishes safely in the background instead of being cut off.
  Kind: fix.
  Source: user-report-2026-07-25.

- ✅ [ONEUP-0043] **Close an orphaned password dialog instead of leaving it on screen.**
  Eleven password dialogs had piled up on the reporter's machine since 10:19,
  and a live verification run left one still open 5.7 hours after it had
  finished cleanly. A dialog whose sudo has exited is one nobody is waiting on,
  and a stack of unexplained password boxes is exactly what makes an updater
  feel untrustworthy. cleanup now closes any askpass process carrying one of
  OneUp's own prompts whose parent is not a waiting sudo. Two false starts worth
  remembering: a "parent is pid 1" orphan check never fires (systemd reparents a
  user session's orphans to `systemd --user`), and matching the helper by a
  leading path misses a script helper, which ps shows as "bash <script>". A live
  dialog with a waiting sudo parent is explicitly left alone, and tested.
  **Layman:** OneUp no longer leaves stray password boxes sitting on your desktop after a run.
  Kind: fix.
  Source: in-session-2026-07-25.

- 📋 [ONEUP-0044] **Find out why the single up-front authentication raises two password dialogs.**
  Measured on a real run: one engine invocation, one `sudo -A -p ... -v` call,
  and yet TWO ksshaskpass processes 16 seconds apart, both carrying sudo_init's
  -p text, both then waiting hours. Confirmed not a fork (one invocation of the
  helper by hand = one process) and not a retry (they overlapped, so both were on
  screen together). Journal shows the run's three privileged commands needed no
  authentication at all, so this is confined to the up-front validate. Suspicion
  falls on `sudo -v` with verifypw=all against multiple password-requiring
  sudoers entries; a scoped `sudo -A -p ... true` may avoid it. Attempts to
  reproduce in isolation raised no dialog at all, so a working harness is the
  first task. ONEUP-0043 removes the visible harm; this is the cause.
  **Layman:** One password request sometimes shows two boxes; only one needs answering. Worth understanding.
  Kind: investigate.
  Source: in-session-2026-07-25.

- ✅ [ONEUP-0045] **Pick up and follow a run that is already in progress when the window opens.**
  Runs deliberately outlive the window (ONEUP-0042), so a relaunched OneUp used
  to look idle and offer a Run button whose only possible outcome was the
  package-lock message — exactly the trap the reporter fell into. The engine now
  records a run in flight (pid, log path, steps) in ~/.local/state/oneup/run.state
  and clears it on exit; a --check or --size run never touches another run's
  record. On startup the GUI finds it, locks the controls, and replays the log
  through the same marker parser the live stream uses, so progress, badges and
  banners all rebuild — then follows new lines every second. A stale record whose
  pid is gone is deleted rather than locking the app out. With no exit code
  available for someone else's process, the run's own @@DONE@@ line is the
  verdict, and a run that never printed one is reported as errors, not success.
  **Layman:** If an update is already running when you open OneUp, it now shows you that run's live progress instead of looking idle.
  Kind: feature.
  Source: user-request-2026-07-25.

- ✅ [ONEUP-0046] **Warn when zypper's wording changes instead of silently showing no progress.**
  The progress display reads zypper's own wording, so an upstream rename makes it
  silently stop — and silence is exactly how the "download size: 0 B" bug hid for
  weeks (ONEUP-0035: zypper renamed "Overall download size" to "Package download
  size", and the test had the old wording baked in so CI stayed green). A
  transaction that installs packages but produces no recognisable progress line is
  the signature of that, so the engine now emits a plain-English hint saying the
  update itself was fine but the progress display needs updating. Tested both
  ways: unknown wording warns and invents no progress, recognised wording raises
  no false alarm.
  **Layman:** If a future zypper renames its output, OneUp says so rather than quietly showing no progress.
  Kind: feature.
  Source: user-request-2026-07-25.

- ✅ [ONEUP-0047] **Add a Stop button that never interrupts an install half-way.**
  There was no way to stop a run, so quitting the app was the only option — which
  is what started this whole incident. Stop is deliberately COOPERATIVE: the GUI
  creates ~/.local/state/oneup/stop.request and the engine honours it only at safe
  boundaries (between steps, and after the repo refresh but before a transaction
  starts), then skips the remaining steps and still prints its summary. Signalling
  the engine instead would either leave rpm half-applied or orphan a zypper that
  carries on regardless — the exact failure of ONEUP-0039/0042. The button, its
  tooltip and the status line all say "after the current step" rather than
  implying an instant abort. A stopped run reports @@DONE@@|stopped, and the GUI
  claims neither success nor failure. A request older than run.state is a
  leftover and ignored — judged by mtime, because deleting stale requests at
  startup would swallow a stop clicked a moment earlier.
  **Layman:** You can now stop an update. It finishes the step it is on first, so nothing is left half-installed.
  Kind: feature.
  Source: user-request-2026-07-25.

- ✅ [ONEUP-0048] **Make a slow mirror legible instead of indistinguishable from a hang.**
  Measured, not assumed: one mirror served an 18 MB repository index at
  930 B/s and another 86 MB of packages at ~18 KB/s, and the app showed
  nothing at all through either. zypper prints a metadata fetch as dots
  with no line ending (no complete line for the GUI to draw) and its
  package prefetch as one line per FINISHED package, ten minutes apart at
  that speed. zypper has no timeout of its own, so left alone it would
  have waited hours.

  Engine: refresh_repos refreshes one repository at a time under
  `sudo timeout $REFRESH_TIMEOUT` (root, so it can kill its own zypper
  child), emits REFRESH|done|total|alias, checks for a stop between
  sources, and offers the existing REMEDY|skip-repo when it gives up.
  Falls back to one bulk refresh if the repository list can't be parsed,
  rather than silently skipping the refresh. PROGRESS gained two optional
  byte fields; both of zypper's total wordings are parsed.

  GUI: a liveness line under the progress bar naming what is being waited
  on, for how long, the size and the rate. The stall clock is stamped on
  the raw chunk before line splitting, because a partial line is the only
  proof of life during a metadata fetch. Where zypper reports no bytes,
  the package cache is weighed against a run-start baseline (world-readable,
  no root; already-cached packages stay inside the baseline).
  **Layman:** OneUp now shows which source it is fetching, the download size and speed, and how long it has been waiting — and gives up on a source that is too slow rather than waiting hours.
  Kind: fix.
  Source: user-report-2026-07-25.

- ✅ [ONEUP-0049] **Open dialogs over the app window on Wayland, where move() is ignored.**
  Every dialog centred itself with widget.move(), which Wayland accepts
  and silently ignores — the compositor owns placement. The same file
  already said so in recenter()'s comment, but the dialogs predated it.

  center_on_parent() now takes the X11 path directly and asks KWin on
  Wayland, matching on transientFor so every dialog is covered including
  the message boxes that have no title of their own, and clamping to the
  screen. Three duplicated showEvent bodies and _center_child collapse
  onto it; run_kwin_script is shared with recenter().
  **Layman:** Settings, Repositories and the message boxes now appear in the middle of the OneUp window instead of wherever the desktop felt like putting them.
  Kind: fix.
  Source: user-report-2026-07-25.

- ✅ [ONEUP-0050] **Stop the test suite reading, and damaging, real machine state.**
  Found while validating the work above, and both halves bit for real in
  the same session:

    * the package-lock probe defaults to /run/zypp.pid, so 40 scenarios
      failed merely because the machine happened to be running zypper —
      precisely when someone is working on an update tool;
    * run.state defaults to the user's own and cleanup() deletes the file
      it owns, so running the suite during a live update DELETED that
      run's record and the window could no longer follow it (ONEUP-0045).

  run_engine now redirects ONEUP_ZYPP_PID_FILE, ONEUP_RUN_STATE and
  ONEUP_STOP_FILE into the mock dir unless the scenario sets them itself.
  The one scenario that invokes the engine directly (the broken-pipe test)
  repeats the overrides by hand.
  **Layman:** The tests no longer depend on what the computer happens to be doing, and can no longer disturb a real update that is running.
  Kind: test.
  Source: in-session-2026-07-25.

- 💭 [ONEUP-0052] **Consider rewriting the Bash engine in Python for finer process control.**
  Raised by the user after ONEUP-0048. Recorded rather than actioned,
  because the evidence cuts both ways and the decision should be made on
  purpose rather than in the middle of a bug fix.
  Decided (2026-07-25): rewrite, on a long-lived `v2` branch. The user
  overruled the "keep separate, don't rewrite" recommendation above, on the
  grounds that difficulty is a cost rather than an objection: v1 already
  exists and keeps shipping from `main`, so building v2 on a branch and
  switching when it is ready carries no delivery risk. That reasoning is
  sound and answers the "what makes it risky" paragraph directly — the risk
  was of shipping a regression, and a branch plus the unchanged 197-test
  suite as the acceptance gate removes it. Design recorded in
  docs/specs/ONEUP-0054-python-engine.md; build tracked as ONEUP-0054. The
  technical caveats above still stand and are restated in the spec's §2 so
  the rewrite is not justified by claims that were never true.

  Not a reason to rewrite: none of that session's faults were Bash's.
  zypper's silence, the mirror's speed and sudo's per-parent-pid
  credential cache are all identical from Python (we would still be
  shelling out to zypper), and the dialog placement bug was in the Python
  half already.

  A real reason to rewrite: supervising the child process. Timeouts,
  reading output as it arrives, cancellation and byte accounting are all
  fiddly in Bash — the per-repository budget had to be routed through
  `sudo timeout` because the shell cannot kill a root child itself, and
  34 privileged call sites each have to stay out of a subshell or they cost
  another password prompt.

  What makes it feasible: the engine suite asserts on the @@MARKER@@
  output, not on Bash internals, so a Python engine could be validated
  against the same suite unchanged.

  What makes it risky: those same tests encode painful, hard-won
  behaviour — the seven-prompt bug, orphaned keep-alives, surviving a
  broken stdout pipe, cooperative stop, lock detection. A rewrite risks
  re-introducing exactly what was just fixed, for a moderate payoff.

  Keep separate from ONEUP-0034 (splitting updater.py). That refactor is
  overdue, independently valuable and far lower risk; it does not need
  this decision made first.
  **Layman:** Weighing whether the part of OneUp that does the actual updating would be better written in Python, like the window is.
  Kind: investigate.
  Source: user-question-2026-07-25.

- ✅ [ONEUP-0055] **Stop the GUI liveness test weighing the machine's real zypper package cache.**
  The same class as ONEUP-0045/0050, which fixed the ENGINE suite's dependence
  on machine state; the GUI suite still had one and it went red mid-session on a
  docs-only commit.

  `_tick_activity` deliberately falls back to `cache_bytes() - _dl_base` during a
  download, because zypper's prefetch phase reports no byte figures at all
  (ONEUP-0048). The liveness test fed `@@PROGRESS@@|…|41943040|397410304` and
  asserted "40 MB of 379 MB", but never called `_reset_activity()`, so `_dl_base`
  stayed at its `__init__` value of 0 while `cache_bytes()` read the real
  /var/cache/zypp/packages. With 44,722,488 bytes of leftovers there from a real
  update, `max(41943040, 44722488 - 0)` won and the line said "44 MB of 379 MB".

  Sharp edge worth remembering: it passed twice earlier in the same session and
  then failed consistently, on identical code. The cache step runs
  `zypper clean --all`, so a real run empties the cache and then refills it — the
  test's verdict tracked which side of that the machine happened to be on.

  Fix: point `updater.ZYPP_PACKAGE_CACHE` at an empty temp dir for the block
  (the neighbouring prefetch-fallback block already did this) and call
  `_reset_activity()`, which every real run does before markers arrive. Both,
  deliberately: the baseline call makes the test match the real code path, the
  temp dir makes the assertion independent of the machine either way.
  Audited the rest of the GUI suite for other real-machine reads — none.
  **Layman:** A test was accidentally reading the real folder where downloaded updates are kept, so it passed or failed depending on what happened to be in there. Now it uses an empty folder of its own.
  Kind: test.
  Source: in-session-2026-07-25.

- 📋 [ONEUP-0054] **OneUp 2.0 — replace the Bash engine with a Python one, on the `v2` branch.**
  Decided in ONEUP-0052. Design: docs/specs/ONEUP-0054-python-engine.md
  (draft — must go through /cold-eyes before any code, global rule 14).

  Shape: update_system.sh (34 privileged call sites) becomes nine
  Python modules under oneup/engine/, keeping the @@MARKER@@ protocol and
  all 13 CLI flags byte-identical. The point of freezing the contract is
  that the existing engine suite then PROVES the rewrite instead of
  being rewritten for it.

  Switch-over gate (all six): G1 engine suite green, no existing assertion weakened; G2 v1 and
  v2 emit the same marker stream under identical mocks (new differential
  harness); G3 GUI suite green driving v2; G4 still exactly one password
  prompt per run; G5 engine imports no Qt and runs with PySide6 absent;
  G6 a real run on the user's machine.

  What the rewrite actually buys, and nothing else is claimed: the
  seven-prompt bug class becomes structurally impossible (one parent pid
  for every privileged child, instead of a discipline 34 call sites must
  each observe); timeouts and cancellation become bookkeeping in one
  runner; the metadata fetch becomes measurable at last, because Python
  can read bytes as they arrive and zypper's dots have no line ending;
  parsers become unit-testable; and two fragile dependencies go away
  (`tee -a -p` and the orphan-prone keep-alive loop). Python does NOT gain
  the ability to kill a root child — `sudo timeout` stays.

  Nine stages; stage 1 (an ONEUP_ENGINE_CMD indirection in the test
  harness) lands on `main` first and ends green there, and every stage
  after it ends with local-CI green on `v2`. `main` ships 1.x throughout; the switch is a 2.0.0
  major bump. Keep ONEUP-0034 (splitting updater.py) separate — it is
  independent and must not be entangled with this gate.
  **Layman:** Rewrite the part of OneUp that does the actual updating in Python, the same language as the window, so the app has finer control over what it is running. Built on a side branch so the current version keeps working until the new one is provably better.
  Kind: implement.
  Source: user-decision-2026-07-25.

- ✅ [ONEUP-0056] **Never report "up to date" for a source the check couldn't read.**
  Reported with two screenshots: OneUp's check said "Everything is up
  to date. 🎉" while Discover listed 8 (finbreak, six 32-bit packman
  libs, and a Discord Flatpak). Root cause was one flaw with three
  faces — the check could not tell "nothing to update" from "I could
  not read the sources", because it discarded stderr (2>/dev/null) and
  never looked at an exit code, then rendered the resulting empty
  answer as a confident all-clear.

  Three independent defects, each able to produce the false all-clear
  on its own, all measured on the reporter's box:

  1. Flatpak: `flatpak remote-ls --updates` abandons the WHOLE listing
     (exit 1, empty stdout) when any one remote lacks a summary file —
     and a local `--no-enumerate` origin, which `flatpak install
     ./app.flatpak` leaves behind, never has one. Six such leftovers
     hid the real Discord update. Now queried per remote, so one dead
     source costs only itself; a no-enumerate origin failing is not
     counted as a failed check, since it serves no listing by design.

  2. System: zypper exits 106 (ZYPPER_EXIT_INF_REPO_SKIPPED) and warns
     on stderr when it sets a repository aside. Both were thrown away,
     so a skipped repo silently contributed zero updates. Verified live:
     microsoft-prod is being skipped on this machine right now for
     "No permission to write repository cache", and nobody was told.

  3. The cache step was wiping the metadata its own check depends on.
     `zypper clean --all` cleans metadata AND packages; the rootless
     --check reads that metadata and cannot rebuild it. So the first
     check after any successful run answered "up to date" regardless
     of truth — which is exactly what happened here: the 22:05 run
     cleaned the cache, and the 10:18 tray check reported 0 into an
     empty directory. Now cleans packages only, matching the step's
     own label ("the downloaded-package cache"). The metadata was
     93 MB of purely re-downloadable data.

  New marker `CHECK_UNKNOWN|key|reason` carries "this answer is not
  trustworthy" to the GUI, which now shows "couldn't check" on the row,
  names the unreadable source in the warning banner, and withholds the
  🎉. The tray tooltip gets the same guard. A count is still emitted
  alongside the warning when updates WERE found — knowing about 7 beats
  knowing about none while a repository is broken.

  Verified end to end against the real machine: the check now reports
  8, exactly matching what Discover found, and names microsoft-prod.
  Regression tests: 3 engine scenarios + 5 GUI assertions (205 and 283
  green).
  **Layman:** OneUp said "Everything is up to date" while 8 updates were waiting — it now says when it couldn't check something instead of guessing.
  Kind: fix.
  Source: user-report-2026-07-26 (screenshots: OneUp "up to date" vs Discover "8 updates").

- 🚧 [ONEUP-0057] **Write the OneUp 2.0 documentation set before any 2.0 code is written.**
  Agreed with the user 2026-07-26. Deliverables, in order: nine standards
  (documentation, coding, security, files-and-naming, testing,
  ui-and-accessibility, wording-and-translation, workflow, plus the existing
  dependencies.md), a marker-protocol reference, the programme design
  (docs/design/oneup-2.0.md, written first), and one spec each for
  ONEUP-0054/0034/0027/0032/0064 (0064 added 2026-07-26 with Task 17). Cold-eyes in three batches, each looped until
  clean (global rule 14); implementation is blocked until then. Build plans
  (docs/plans/) are deliberately NOT written now — each is written when its
  item starts.
  Decision (2026-07-26, superseding the same day's earlier call): v1 freezes.
  main ships 1.4.0 first — the eight finished-but-unreleased improvements from
  ONEUP-0045/0046/0047/0048/0049/0050/0055/0056 — then takes a change ONLY when
  1.x cannot do its job, i.e. people can no longer install system, Flatpak or
  firmware updates (user's definition; a silent wrong verdict and a machine left
  damaged both count, as does zypper changing its output and blinding 1.x).
  With main near-idle, the merge-pain argument for landing the GUI split
  (ONEUP-0034) on main is gone, so the split moves back to v2 as its first
  substantial work. See docs/design/oneup-2.0.md §5.3/§5.4.
  Progress (2026-07-26): the standards set gained three structural rules
  and the gate that enforces the countable half of them — a rule with no
  check is a wish (every standard now ends with a "What checks this"
  table, naming honestly the rules nothing catches); §6b, which keeps
  most code-derived counts out of a document altogether; and one-owner-
  per-fact plus the blast-radius rule. `tests/docs-check.py` runs in
  `local-CI.sh` with eight checks, each proved to fail on a seeded fault.
  Progress (2026-07-27): Task 13 done — cold-eyes batch 2 over the 2.0
  design, the engine spec and workflow.md. Nine loops to convergence
  (eight full, one cheap closing pass); ~380 findings raised, ~330
  verified and fixed. Nothing a loop fixed ever resurfaced. All three
  flipped Draft to Reviewed, so ONEUP-0054 is unblocked.

  The four that mattered were each a document claiming cover it did not
  have: _paint_state_shape called "symmetric by construction" when it is
  handed like the knob; the engine spec citing the marker reference as
  owning a state-file contract that reference had delegated TO the spec,
  so it existed in neither; workflow.md crediting bump-test.py with
  proving all six version sites when five of its six assertions read the
  CHANGELOG; and G4 said to gate ONEUP-0044 while its scenario counts
  authentications and the bug is two dialogs from one.

  Two gaps closed rather than reworded: nothing said how 2.0.0 is
  released (release.sh refuses any branch but main), and the retained
  Bash fallback stops being a drop-in once ONEUP-0072 converts the
  payloads to codes, which is inside 2.0.

  Two decisions with the user: update_system.sh stays through 2.0 and
  goes in 2.1; workflow.md 1.2 gains one narrow freeze exception, for the
  ONEUP_ENGINE_CMD harness change only.

  Lesson for Tasks 14-19: loops 5-8 mostly reviewed the previous loop's
  edits, not the documents. Every critical from loop 5 on was introduced
  by an earlier fix. Fix by deleting and pointing; sweep every citation
  of a changed fact in the same pass; never answer a finding with a new
  paragraph.

  Still open: Task 14 (the GUI-split spec) through Task 19.

  Cold-eyes: 4 loops, 6 lanes, converged on polish. 27 findings raw, 22
  verified, 5 dismissed. The two that mattered most were both false
  assurances: the marker gate was comparing the contract table against
  the engine's own header comment — which the contract document records
  as stale — and `testing.md`'s new table stated the opposite of the
  truth about which suite redirects HOME. Also found: README said OneUp
  does "four things" and listed five; `workflow.md` claimed the version
  lockstep covered the CHANGELOG links and it did not (ONEUP-0033's
  failure mode, ungated). Filed ONEUP-0069 for the DISK marker.

  Still open: Task 11 (rewrite CLAUDE.md as a map) through Task 19.

  Decisions taken with the user in the same session, recorded in the design:
  2.0 is a full feature release (engine rewrite + GUI split + themes + i18n +
  the double-prompt fix + a dependency refresh, list open); nothing ships as
  2.0 until it fully replaces v1; main keeps shipping 1.x meanwhile; the GUI
  split (ONEUP-0034) lands on main first, because it changes no behaviour and
  branching v2 from already-split code is what keeps months of merges sane;
  CLAUDE.md shrinks to a map that still carries the hard-won traps.
  **Layman:** Write down the design and the rules for version 2 before building it, so every piece is built to the same standard.
  Kind: doc.
  Source: user-request-2026-07-26.

- 📋 [ONEUP-0058] **Stop the test suite creating ~/Documents/update-logs on the real machine.**
  update_system.sh:149 runs `mkdir -p "$LOG_DIR"` before checking whether
  --log= was passed, and LOG_DIR ($HOME/Documents/update-logs, line 55) has NO
  environment override. tests/run-tests.sh's run_engine (lines 56-72) redirects
  ONEUP_ZYPP_PID_FILE / ONEUP_RUN_STATE / ONEUP_STOP_FILE but not HOME, so every
  engine scenario creates that directory on whatever box the suite runs on.
  Nothing is written there (--log= is always supplied), but it still breaks the
  standing rule that a test must never depend on, or damage, the state of the
  machine it runs on. Fix in the 2.0 Python engine (ONEUP-0054): either give the
  directory an ONEUP_* override, or create it only immediately before writing to
  it. Do not fix on main, which is frozen at 1.4.0.
  **Layman:** Running OneUp's tests currently creates a folder in your Documents, even if you have never used the app.
  Kind: fix.
  Lanes: engine, tests.
  Source: in-session-2026-07-26 (writing docs/standards/files-and-naming.md).

- 📋 [ONEUP-0059] **Honour XDG_STATE_HOME instead of hard-coding ~/.local/state.**
  updater.py:117 builds STATE_DIR from Path.home() / ".local" / "state" /
  "oneup" and never reads XDG_STATE_HOME; tests/gui-smoke.py:31-32 exports both
  XDG_CONFIG_HOME and XDG_STATE_HOME into its sandbox, so those two lines read as
  protection they do not actually provide -- the isolation works only because
  line 30 also rewrites HOME. Two things to fix together: make the app follow the
  XDG base-directory specification, and make the sandbox's exports meaningful
  (or drop them). Lands with the GUI split (ONEUP-0034), whose module-level path
  constants this touches.
  **Layman:** OneUp ignores the standard setting that tells apps where to keep their working files.
  Kind: fix.
  Lanes: gui.
  Source: in-session-2026-07-26 (writing docs/standards/files-and-naming.md).

- 📋 [ONEUP-0060] **Pin PySide6 and PyInstaller in the AppImage build.**
  packaging/appimage/build-appimage.sh:22 runs `pip install --quiet
  pyinstaller PySide6` with no version constraint, inside a fresh venv, on
  every tagged release. Three consequences, all measured against the file
  on 2026-07-26: (1) the AppImage attached to a tag is NOT reproducible —
  rebuilding v1.4.0 tomorrow can bundle a different PySide6 than the one
  users downloaded; (2) a broken or compromised upstream release lands in
  users' AppImages automatically, with no gate; (3) it contradicts
  docs/standards/dependencies.md, whose known-incompatibility ledger
  assumes a version can be pinned away from — you cannot pin away from a
  bad version if you never pin at all. The RPM path is unaffected (it
  Requires python3-pyside6 and takes the distro's). Fix: pin both to an
  exact version in the build script (or a requirements file it installs
  from), and treat the bump as ordinary ledger-governed dependency work.
  Not fixable on frozen main; lands with the 2.0 packaging pass.
  **Layman:** The downloadable app is rebuilt against whatever version of its toolkit is newest that day, so two builds of the same release can differ — pin the versions so a release is reproducible.
  Kind: security.
  Source: in-session-2026-07-26 (ONEUP-0057 Task 3 gotcha sweep).

- 📋 [ONEUP-0061] **Migrate QSettings if 2.0 renames the settings organisation.**
  updater.py constructs QSettings("OneUp", "OneUp") at four sites (522,
  1008, 1299, 3698), which writes ~/.config/OneUp/OneUp.conf — verified
  present on this machine, holding geometry, repos_geometry, log_shown and
  tray_enabled. Every other artefact uses the app ID
  za.co.antsprojectshub.OneUp (desktop file, icon, metainfo) and runtime
  state uses ~/.local/state/oneup/, so the settings path is the one
  outlier. docs/standards/files-and-naming.md makes that inconsistency
  visible, and the natural 2.0 tidy-up is to switch the organisation to
  the app ID. Doing so with no migration silently resets every existing
  user's preferences: the tray toggle turns itself off, window geometry
  is forgotten, the text-size choice reverts. Requirement for 2.0: either
  leave the organisation string alone and document why, or copy the old
  keys across on first run before reading them. Whichever is chosen, the
  GUI suite needs a regression check that an old-format config is still
  honoured.
  **Layman:** The app's saved preferences live under a folder name that doesn't match the app's official ID; tidying that up in 2.0 would silently wipe everyone's settings unless we copy them across first.
  Kind: implement.
  Source: in-session-2026-07-26 (ONEUP-0057 Task 3 gotcha sweep).

- 📋 [ONEUP-0062] **Silence the teardown tracebacks the GUI suite prints while passing.**
  Measured 2026-07-26: `QT_QPA_PLATFORM=offscreen python3 tests/gui-smoke.py`
  printed 56 Traceback / RuntimeError lines and exited 0. That figure was one
  observation — the count varies run to run and drifts as the suite grows, so
  `docs/standards/testing.md` §7 owns the measurement and how to take it. All of them are
  `RuntimeError: libshiboken: Internal C++ object (QProcess) already
  deleted`, raised from the lambda at updater.py:2461 (and the same shape
  at the other six QProcess sites). Cause: the QProcess is parented to the
  window, so when a test drops the window while a probe is still running,
  Qt deletes the child C++ object but the pending `finished` connection
  still fires into Python. The docstring at 2448 shows the author already
  considered teardown for incremental reads — the `finished` slot itself is
  the gap. Two reasons to fix rather than tolerate: (1) a passing suite
  must be silent, or a genuine regression hides in the noise, which is the
  rule docs/standards/testing.md will carry (ONEUP-0057 plan, Task 5); (2)
  the same ordering can bite in production if the user quits while an
  auth-status probe is in flight. Likely fix: disconnect (or guard the slot
  with a shiboken.isValid check) in closeEvent, plus a test assertion that
  stderr is empty. Not fixable on frozen main.
  **Layman:** The window tests print 56 alarming error reports and then say everything passed — which trains us to ignore errors, so a real one would slide straight past.
  Kind: test.
  Source: in-session-2026-07-26 (ONEUP-0057 gotcha sweep).
  Note (2026-07-26): the headline's "56" is a single observation, not a
  stable figure. Measured four times at `58ea3bc` the count was 30, 30,
  30, 31 — it varies run to run, because the tracebacks come from
  parented QProcess objects torn down in a non-deterministic order.
  `docs/standards/testing.md` §7 owns the measurement and its derivation;
  treat this bullet's number as the symptom that opened the item.

- 📋 [ONEUP-0063] **Add pyproject.toml so local lint and CI check the same rules.**
  Verified 2026-07-26: the repo has no pyproject.toml, no requirements
  file and no setup.py. local-CI.sh:78 runs `ruff check . --select F,B
  --exclude screenshots -q`, so the rule set lives only in that one
  script. Consequences: a contributor running plain `ruff check .` gets
  ruff's defaults and disagrees with CI in both directions, with no
  warning; and the six `# noqa: S` comments at updater.py 580, 583, 585,
  985, 1925 and 3333 currently suppress nothing at all, because S
  (bandit/security) is not among the selected rules — they read as
  evidence that a security review happened when none is enforced.
  docs/standards/coding.md §2.1 already settles the exact contents
  (target-version py313, line-length 100, select F,B,S,E,W,I,UP,RUF) and
  §10 records both as traps. Work: add the file, drop the --select and
  --exclude flags from local-CI.sh, and fix whatever the newly-enabled
  rules surface — measured as 13 over-long lines tree-wide at 100 columns.
  Not landable on frozen main; part of the 2.0 opening pass.
  **Layman:** Running the code checker yourself gives different answers than the build server does, and six safety comments in the code silence a rule that isn't switched on — one small config file fixes both.
  Kind: chore.
  Source: in-session-2026-07-26 (ONEUP-0057 Task 3).

- 📋 [ONEUP-0064] **Redesign the interface around ergonomics, plain-language clarity and accessibility.**
  Requested by the user (2026-07-26) as part of 2.0, not as polish
  afterwards. Three stated priorities, in the user's order: ergonomics,
  user-friendliness, accessibility.

  HARD CONSTRAINT, stated by the user and CLARIFIED 2026-07-26: no
  FOCUS borders. Ordinary borders are fine and always were — a button
  may look like a button, a card may have an edge. What must not appear
  is a border/outline drawn to mark the focused or highlighted control.
  This is the existing no-focus-ring decision (2026-07-25, CLAUDE.md:
  the app deliberately draws no focus ring; focus reuses the hover
  look), restated, not widened. An earlier revision of this bullet read
  it as "no borders on buttons or links at all" — that was my
  over-reading of the original wording, corrected by the user the same
  day.

  The accessibility consequence still has to be answered head-on rather
  than waived, because it is the focus indicator specifically that is
  off the table: WCAG 2.2 SC 2.4.11 wants focus not obscured and SC
  1.4.11 wants a visible non-text indicator. The spec must show how a
  keyboard-only user can tell where they are without a ring — the hover
  treatment (fill and contrast shift) is the existing answer and the
  likely one, and whatever is chosen must be MEASURED, not asserted.

  Two further decisions from the user (2026-07-26):
  - FREE REIN on the redesign itself. No layout question needs to be
    asked up front; propose and build, and we tweak afterwards. This
    removes the "how far may the layout move" question the spec task
    was going to ask.
  - KEEP the phone-style on/off switches. The user has always preferred
    them to checkboxes, specifically because on/off is easy to see at a
    glance. They are a fixed point of the design, not a candidate for
    replacement — and their state must stay readable without relying on
    colour alone (ONEUP-0028), which the current high-contrast property
    already handles.

  Interacts with three other 2.0 items and the sequencing matters:
  - ONEUP-0034 (GUI split) comes FIRST — redesigning a 3,719-line module
    and splitting it at the same time makes both unreviewable.
  - ONEUP-0027 (themes) comes AFTER — theming a layout that is about to
    change means doing it twice.
  - ONEUP-0032 (translation) comes after both, unchanged: the redesign
    rewrites user-facing strings, and wrapping them for translation
    before that means wrapping them twice.

  Governed by docs/standards/ui-and-accessibility.md (ONEUP-0057 plan,
  Task 6) and specced at Task 17. ONEUP-0028's three groups (blind,
  partially sighted, colour-blind) remain the accessibility floor: every
  existing guarantee — accessible name on every focusable widget, never
  signalling state by colour alone, font sizes derived from the desktop
  point size — is a regression test the redesign must still pass, not a
  starting position to renegotiate.
  **Layman:** Rework the window so it is easier and more comfortable to use — clearer wording, less reaching, everything usable by keyboard and screen reader — without drawing boxes around buttons and links.
  Kind: ux.
  Source: user-request-2026-07-26.
  Ringless focus cue — measured 2026-08-03, before the spec is written, because
  it changes what the spec can propose. ui-and-accessibility.md section 5.4
  records the gap (SC 2.4.13 wants 3:1 between focused and unfocused states;
  three of four shipped controls measure 1.14-1.62:1) and assigns closing it to
  this item. Reproduced those four figures exactly, then measured the candidate
  space, and the result rules out the obvious answer:

    rest #4aa3ff -> #5cb0ff   1.14:1   (today: focus lightens, like hover)
    rest #4aa3ff -> #ffffff   2.63:1   FAILS -- pure white is the limit
    rest #4aa3ff -> #0d4d8c   3.24:1   passes
    rest #4aa3ff -> #0a4278   3.86:1   passes

  So a focus cue on the blue buttons CANNOT be built by lightening: white
  itself is only 2.63:1 against the rest fill, so no lighter shade reaches 3:1
  at any saturation. The cue must darken, or the rest colour has to change.
  That inverts the current instinct, where focus lightens exactly as hover
  does — and it means "focus reuses the hover look" (CLAUDE.md, the 2026-07-25
  decision) cannot survive contact with SC 2.4.13 on these palettes. The
  no-focus-BORDER constraint is untouched by this; darkening a fill draws no
  ring.

  The spec has to settle it across all eight themes ONEUP-0027 ships, not just
  the default, and add the ratio computation to the suite rather than asserting
  it -- section 5.4 already says the measurement is what was missing.

  Method: WCAG relative-luminance formula, sRGB, computed rather than eyeballed.

  SPLIT 2026-08-03. The focus cue left this item for ONEUP-0076 after the spec
  converged by cap rather than clean at three cold-eyes loops and 762 lines,
  with fix collateral outrunning draft defects two loops running (24 -> 13 -> 8
  draft against 0 -> 21 -> 27 collateral). Across three loops and nine lanes
  essentially every finding fell in the focus half. This item keeps the LAYOUT
  redesign -- header, Settings grouping, action row, the whole-row click target,
  tab order and target sizes -- at docs/specs/ONEUP-0064-interface-redesign.md,
  now 268 lines with five invariants. The measurement recorded above is
  ONEUP-0076's and is restated there; it is kept here because it is the reason
  the split happened. Neither half's gate has run against its own bytes yet:
  both enter Task 18 of the ONEUP-0057 plan from loop 1.
  Spec written and gated 2026-08-03: docs/specs/ONEUP-0064-interface-redesign.md,
  Status Draft, converged BY CAP after three cold-eyes loops rather than clean
  (24, 34, 35 verified). Not blocked -- nothing verified is left unfixed -- but
  its section 11 recommends a split before implementation, and that
  recommendation is the main output of the run.

  The measurement on this bullet held and became the design. Because lightening
  cannot reach 3:1 on the accent at any shade, the app DERIVES a focus colour
  instead of authoring one per theme: the smallest blend toward black, or toward
  white where black cannot get there, clearing 3:1 against every one of the
  control's rest pixels. That is total for a single surface -- max(contrast vs
  black, vs white) never drops below 4.58:1 -- so a palette nobody has written
  yet still gets a working cue, which is what ONEUP-0027's six new themes need.
  The same bound gives the label colour for free.

  What the loops changed most: the totality claim was single-surface while the
  rule was multi-surface, and multi-surface is NOT always satisfiable (#000000
  and #989898 admit no fill; 192 such grey pairs). The search now fails loudly.

  Two corrections to OTHER documents came out of it, both verified:
  ui-and-accessibility.md 5.4 says "SC 2.4.7 (Focus Visible) is still met" and
  that is false -- 16 of the window's 34 focusable widgets have no cue at all,
  including all five toggle switches -- and ONEUP-0028 section 5 promises :focus
  rules for eight styled controls when three of them have none, and specifies a
  2px accent outline the no-focus-ring decision forbids. ONEUP-0028's own
  section 2 had already recorded the absence as a "WCAG 2.4.7 failure", which
  corroborates it. Both edits are listed in the spec's section 8 and land with
  implementation, not now (main is frozen; this is v2 work).

  Split recommendation: the focus-cue contract (4.1-4.4, INV-1..5, 8, 11, 13) and
  the layout redesign (4.5, INV-6, 7, 10, 12) are a clean seam. Across three
  loops and nine lanes essentially every finding fell in the focus half. Trend:
  draft defects 24 -> 13 -> 8, fix collateral 0 -> 21 -> 27, document 495 -> 762
  lines. Awaiting the user's decision.

- 📋 [ONEUP-0065] **Convert the remaining line-number citations in the older documents to symbol names.**
  docs/standards/documentation.md 6a (added 2026-07-26, the user's
  decision) requires a citation to name a symbol or quote a searchable
  anchor, never a bare line number. All seven standards were swept in the
  same commit (0812d81).

  Not yet swept, measured at 0812d81: ONEUP-0022 plan (30), ONEUP-0018
  spec (27), ONEUP-0022 spec (18), ROADMAP.md (10), ONEUP-0028 spec (10),
  ONEUP-0025 spec (10), ONEUP-0018 plan (9), ONEUP-0057 plan (8),
  the 2.0 design doc's three (updater.py:699, line 712, lines 692-697 —
  added to this bullet's scope by the cold-eyes batch-1 sweep),
  ONEUP-0054 spec (7), the 2.0 design doc (1) — 130 in total.

  Two of those counts are absorbed elsewhere rather than by this item:
  ONEUP-0054's 7 were rewritten by ONEUP-0057 Task 12 on 2026-07-27 — done,
  leaving 62 across four specs —
  and the ONEUP-0057 plan's 8 are verification commands rather than prose
  citations, which the standard permits.

  Deliberately deferred rather than done in the sweep: the 0018/0022/0025
  documents describe already-shipped work, so their citations are read
  rarely and rot harmlessly. The ones that matter are the documents 2.0 is
  built from, and those are now clean. Do this before the GUI split
  (ONEUP-0034) lands, since that is what turns every remaining line number
  into a pointer at a file that no longer exists.
  **Layman:** Make the older design notes point at code by name instead of by line number, so they don't go wrong the moment the code shifts down a few lines.
  Kind: doc-fix.
  Source: user-request-2026-07-26.

- 📋 [ONEUP-0066] **Correct the engine's abbreviated marker list when the Python engine replaces it.**
  update_system.sh's header comment lists the markers for a reader's
  convenience. Measured at b3ede2d while writing
  docs/reference/marker-protocol.md, three entries are wrong, and each
  would make somebody write a broken parser:

  - STEP_END is listed as `key|ok|skip|fail|detail`, implying five
    fields. It is three: `key|status|detail`, where status is one OF
    ok/skip/fail.
  - REPO is listed as `warn|reason`. It is `warn|duplicate|urls`, and
    the GUI reads that third field.
  - DONE is listed as `ok|errors`. `stopped` is a third value — and the
    one with a behaviour rule attached (the GUI must claim neither
    success nor failure).

  Not fixed at discovery: main is frozen (workflow standard 1), and none
  of the three is a defect in running code — the emitters and the parser
  agree; only the comment is stale. ONEUP-0054 replaces this file
  outright, so the fix belongs to the rewrite: the Python engine carries
  the corrected list, or drops the comment and points at the reference.
  Until then docs/reference/marker-protocol.md 7 records the drift and is
  the authority.
  **Layman:** The update script has a quick summary of its own progress messages at the top, and three lines of it are out of date.
  Kind: doc-fix.
  Source: in-session-2026-07-26 (ONEUP-0057 Task 9, writing the marker reference).

- 📋 [ONEUP-0067] **Stop the GUI smoke suite making live GitHub requests.**
  Updater.__init__ calls _check_app_update() unconditionally, which issues
  a QNetworkAccessManager GET to api.github.com/repos/<slug>/releases/latest.
  tests/gui-smoke.py constructs updater.Updater() 49 times and stubs
  nothing — no monkeypatch of _check_app_update, no QNetwork fake — so a
  suite run makes 49 live requests.

  Three costs, in order: the suite is silently network-dependent, so it
  fails differently offline than on; GitHub rate-limits unauthenticated
  calls, so a loop of runs can start failing for a reason unrelated to the
  code; and docs/standards/testing.md 2.3 states "no test may reach the
  network" as an absolute, which was false when it was written.

  The standard now names this as a known exception rather than pretending
  the rule holds. Fix belongs on v2 (main is frozen): either stub the check
  in the suite, or give _check_app_update a skip when a test environment is
  detected — the suite already rewrites HOME before importing, so a
  sentinel is available.
  **Layman:** The window's test run quietly phones GitHub 49 times to ask whether a newer OneUp exists.
  Kind: test.
  Source: cold-eyes-2026-07-26 batch 1, testing-standard lane CRITICAL.

- 📋 [ONEUP-0068] **Replace the orphaned-dialog scenario's sleep with a poll, and make its SKIP branch loud.**
  The scenario "an orphaned password dialog is reaped when the run ends"
  stages two background processes, then does a bare `sleep 0.5` IN THE
  SCENARIO BODY before pgrep-ing for their children. docs/standards/
  testing.md 6 forbids exactly this — poll for a condition, never sleep for
  a duration — and the scenario is the only place in either suite that
  breaks it.

  The second half is worse than the first: when the race is lost it prints
  "SKIP - could not stage the dialogs" and increments NEITHER pass nor
  fail. So a run that reports a green 205 can silently have made 203
  assertions, and nothing says so. A skip that costs coverage must be as
  visible as a failure.

  Fix: poll for the child pid with a ceiling (the pattern the rest of the
  suite uses), and make the give-up path a FAIL — if the fixture cannot be
  staged, the test cannot prove what it claims.
  **Layman:** One test waits half a second and hopes; when the guess is wrong it quietly skips instead of failing.
  Kind: test.
  Source: cold-eyes-2026-07-26 batch 1, testing-standard lane HIGH.

- 📋 [ONEUP-0069] **Cover the DISK marker in the engine test suite.**
  The engine emits 23 markers via the `marker NAME "payload"` helper.
  `tests/run-tests.sh` asserts on 22 of them; **DISK** is the exception.
  It fires only from the pre-flight low-disk check, which no scenario
  arranges, so nothing proves the engine still produces it. The GUI half
  IS covered — `tests/gui-smoke.py` feeds `@@DISK@@|warn|/|512 MiB` and
  asserts the banner — which is what made the gap easy to miss: the
  marker looks tested when you grep the suite as a whole.

  Add a scenario whose mock puts a mount under the pre-flight threshold
  and assert the `@@DISK@@|warn|<mount>|<free>` line. Then delete DISK
  from `KNOWN_UNTESTED_MARKERS` in `tests/docs-check.py`, which fails the
  build if any other marker ever loses its coverage.

  Found by the cold-eyes pass on the documentation set, checking the
  claim in `docs/reference/marker-protocol.md`'s "What checks this" table
  that `tests/run-tests.sh` proves the engine emits each marker. It did
  not, for one of the 23.
  **Layman:** One of the messages the updater can send — the warning that your disk is nearly full — is never exercised by the automated tests, so a change could break it without anything noticing.
  Kind: test.
  Source: cold-eyes-2026-07-26 lane-6 (ONEUP-0057 documentation set).
  Progress (2026-08-03): the blocker is gone. This item needed a scenario to
  arrange a mount under the pre-flight threshold, which was impossible while
  `df` was unmocked — the engine read the real machine. The /test-audit sweep
  added a `df` mock to `setup_common` (reporting ample space) for a different
  reason: unmocked, a developer's nearly-full disk injected a real @@DISK@@|warn
  line into every system-step scenario. A DISK scenario can now overwrite that
  mock the way scenarios overwrite `zypper`, then drop DISK from
  KNOWN_UNTESTED_MARKERS in tests/docs-check.py. Still open.

- 📋 [ONEUP-0070] **Cover the absent-tool skip path in the engine test suite.**
  Found while revising the ONEUP-0054 spec (2026-07-27, verified at b6d37ed).
  update_system.sh guards the Flatpak and firmware steps with `command -v
  flatpak` and `command -v fwupdmgr`, and both CLAUDE.md and the spec state
  the rule that an absent tool is skipped cleanly, never errored. No
  scenario in tests/run-tests.sh arranges an absent tool: every mock
  directory provides both, so the skip branch has never run under test.

  Worth one scenario per tool: a mock PATH without the binary, asserting the
  step reports skipped rather than failed and the run still ends ok. It is
  also the branch a real user on a Flatpak-less machine takes on every run,
  so it is not an edge case for them.

  Carried into 2.0 as INV-9 of docs/specs/ONEUP-0054-python-engine.md, where
  it is recorded honestly as having no test. Fix it on `v2`, at that spec's
  §4.6 stage 2, before G1 — the freeze's one exception names a different
  change (docs/standards/workflow.md 1.2), and the rewrite must not inherit
  an untested branch it is expected to reproduce byte-identically.
  **Layman:** Prove that OneUp quietly skips the Flatpak and firmware steps on a machine that doesn't have those tools, instead of reporting a failure.
  Kind: test.
  Source: in-session-2026-07-27 (ONEUP-0057 Task 12).

- 💭 [ONEUP-0071] **Publishing OneUp on Flathub, or packaging it for other distributions — considered and declined.**
  The user's decision, 2026-07-27. Recorded as considered rather than
  planned so the reasoning is findable, and so the question has a dated
  answer instead of looking like nobody thought of it. The rule itself lives
  in docs/standards/workflow.md 8.1, which owns it; this bullet is the
  record, not the rule.

  Nothing had proposed it. Raised by the user unprompted, and worth writing
  down for exactly that reason.

  Two independent reasons, either sufficient. (1) A Flatpak is sandboxed and
  every one of OneUp's five steps acts on the host: zypper and
  `flatpak update --system` go through sudo, and fwupdmgr reaches the same
  host state via fwupd's system daemon. A sandboxed build would have to hole
  its own confinement to do its job. (2) The other distributions do not need
  it — the user tested them and their update paths are already fine. OneUp
  exists because Tumbleweed's graphical tools get the system update wrong;
  that is an openSUSE problem, so the answer is an openSUSE app.

  Does NOT touch the `flatpak` STEP. OneUp still updates the Flatpaks
  installed on the user's machine; that is unaffected and unrelated beyond
  sharing a word.

  Reopen on a new reason, not a new opinion: a distribution whose own update
  path is broken the way Tumbleweed's was, or a confinement technology that
  can grant host package-manager access without pretending to be a sandbox.
  The three shipping paths stay the AppImage, the RPM and the OBS repo.
  **Layman:** OneUp stays an openSUSE app, installed the three ways it already is. It won't be put on Flathub, because the app needs to change the whole machine and a Flathub app is deliberately walled off from doing that — and the other Linux systems already update themselves fine.
  Kind: package.
  Source: user-request-2026-07-27.

- 📋 [ONEUP-0072] **Turn the engine's prose marker payloads into stable codes the window words itself.**
  Split out of ONEUP-0032 at its fifth cold-eyes loop: the item held two
  contracts, and every finding in loops 4 and 5 sat on this side of the seam.
  ONEUP-0032 keeps the catalogue machinery and right-to-left; this item takes
  the engine-to-window payload conversion.

  Every payload field the window renders as words becomes a stable code, and
  the wording moves to the window. Wider than
  docs/reference/marker-protocol.md section 5.1 currently reserves, and for a
  reason that is not translation: the window already re-derives STEP_END's
  meaning by matching English substrings in the engine's sentence, so the
  coupling is a live defect on its own.

  Also in scope: the desktop notification the two systemd timers raise, which
  the engine composes in English today and which never travels as a marker at
  all.

  Spec to be written; the cold-eyes log in docs/specs/ONEUP-0032-i18n.md
  loops 1 to 5 records what was already found and settled for it.
  **Layman:** Right now the update engine writes the English sentences you see on screen. Move that wording into the app so it can be translated — and so a reworded engine message stops silently changing what a task's badge says.
  Kind: refactor.
  Source: split out of ONEUP-0032 during its cold-eyes review, 2026-07-27.
  Spec written and reviewed (2026-08-03): docs/specs/ONEUP-0072-marker-codes.md,
  Status Reviewed. Three cold-eyes loops of its own (24, 22, 20 verified;
  1, 0, 1 dismissed), on top of loops 1-5 taken as part of ONEUP-0032 before
  the split. Loop 3 converged BY CAP, not clean — section 11 carries the tail
  and recommends splitting section 4 rather than running a fourth loop, since
  the document reached 654 lines.

  Ordering settled by the user the same day: this item lands BEFORE ONEUP-0032,
  between the engine rewrite and translation. Both specs had claimed the other
  must land first. docs/design/oneup-2.0.md section 5.2 owns the order and now
  places this item in its diagram, which it had never done.

  Three contract decisions an implementer needs and would otherwise invent:
  the REBOOT reason carries two disjoint vocabularies (four joinable components
  from the transaction log, plus two standalone reasons), status still decides
  the badge for fail and skip while the code decides it only for ok, and the
  marker emitter must take its fields as separate arguments — today's takes a
  pre-joined payload, so the one-place pipe guard INV-2 requires is otherwise
  unimplementable. That last one touches every marker call site.

  Scope is wider than docs/reference/marker-protocol.md section 5.1 reserves;
  that reference, oneup-2.0.md section 5.1 and testing.md section 5 are all
  amended in the same commit as the code.

- 📋 [ONEUP-0073] **Skip the cache clean when an earlier step failed.**
  The cache step is guarded by `step_selected cache && ! stop_pending` only —
  it never consults whether an earlier step failed. So a `zypper dup` that
  aborts mid-transaction is followed immediately by a clean that discards
  every package the failed run had successfully downloaded.

  Observed on a real run: the system step failed after preloading 73.2 MB,
  and the cache step then reported `Reclaimed 74M from the package cache`.
  The retry re-downloaded all of it.

  The engine header states the deliberate intent that "the end-of-run summary
  and cache cleanup still happen" after a step fails. That reasoning holds for
  a flatpak or firmware failure; it does not hold when the *system* step failed,
  because the cached packages are exactly the retry's input. Narrow the rule
  rather than reversing it: skip the clean when the system step failed, and say
  so in the summary so the skip is not mistaken for the step not running.
  **Layman:** If the update fails, OneUp should keep the packages it already downloaded so retrying is quick, instead of deleting them.
  Kind: fix.
  Source: in-session-2026-07-31 (real run 2026-07-31_074230).

- 📋 [ONEUP-0074] **A run the user stopped notifies "Already up to date".**
  Found while writing docs/specs/ONEUP-0072-marker-codes.md; filed by that
  spec's section 10 as out of its scope, because section 3.2 forbids it
  re-wording anything it converts — its gate is that behaviour did not
  change, so it carries the wrong sentence across unchanged.

  The engine already knows. update_system.sh emits marker DONE "stopped"
  when STOP_HONOURED is true, deliberately claiming neither success nor
  failure. Twenty lines further on, the end-of-run notification block
  falls through four cases -- errors, a non-zero installed count, either
  changed flag, else "Already up to date" -- and has no stopped branch at
  all. So an interrupted run that installed nothing before it stopped is
  announced as needing nothing.

  Small, because nothing needs discovering: the verdict exists at the
  point the notification is built (the same function has STOP_HONOURED in
  scope), and the window holds @@DONE@@'s verdict in _done_status. It
  needs one more branch and its sentence -- something on the order of
  "Update stopped -- the steps that ran are in the log."

  FOLDED INTO ONEUP-0077 on 2026-08-03. That decision went the way this
  bullet anticipated: ONEUP-0072's section 4.4 was split out, and the new
  item rebuilds the same four-case fall-through in the window, so the
  stopped branch is written there rather than twice. This bullet stays as
  the record of the defect and its measurement; the work is ONEUP-0077's
  and its INV-1 is the test named below. main is frozen and this does not
  qualify (nobody is blocked from updating), so it is 2.0 work either way.

  Test: a scenario in tests/run-tests.sh that stops a run at a step
  boundary and asserts the notification text is not "Already up to date";
  today the suite's _notify_case coverage checks the three reachable
  texts and never exercises the stopped path.
  headline_only
  **Layman:** If you stop an update part-way, the desktop notification says everything was already up to date — which is not what happened.
  Kind: fix.
  Source: oneup-0072-cold-eyes-loop-3-2026-08-03.

- 📋 [ONEUP-0075] **No OneUp spec's invariant list can be read by spec_query.**
  Found by /doc-lint's structure check while writing
  docs/specs/ONEUP-0064-interface-redesign.md. Its checks.md calls this exact
  signature a finding: invariants_count 0 together with a non-zero
  possible_untabled_invariants means the parse failed, and "a doc whose
  contract list no tool can read is not implementable".

  It is not one spec. Measured 2026-08-03 against every spec in docs/specs/:
  ONEUP-0064 reports invariants_count 0 with possible_untabled_invariants 10,
  and ONEUP-0027 -- Status Reviewed after four cold-eyes loops -- reports 0 and
  12. The verb reads title, status and kind correctly in both cases, so it is
  the invariant list specifically that it cannot see.

  Not caused by the specs being wrong. documentation.md section 5 mandates the
  bullet form deliberately, on the stated grounds that "a table cell cannot hold
  the detail a real invariant needs", and every spec follows it:

    - **INV-1** Every theme supplies every key in the reference set, and no extra.
      *Test:* ...

  spec_query's own description names a bullet form of "- **INV-N** - body" with
  an em-dash separator. That is NOT the cause: a scratch copy of ONEUP-0064 with
  the em-dash inserted on all ten bullets still parses to 0. So the mismatch is
  deeper than the separator and was not diagnosed further -- diagnosing it is
  part of this item, not a precondition for filing it.

  Three ways out, and picking one is the work: teach the parser this project's
  form; add a machine-readable line per invariant alongside the prose; or accept
  the gap and stop treating spec_query as a gate for this project, recording that
  in documentation.md so the next session does not re-find it.

  Costs nothing today because no gate depends on it -- tests/docs-check.py does
  its own parsing and passes. It costs later, when a spec's invariants are meant
  to be cross-checked against tests by anything other than a person reading both.

  Test: spec_query on any file in docs/specs/ returns invariants_count equal to
  the number of INV-N bullets it contains, rather than 0.
  headline_only
  **Layman:** The tool that is supposed to list a spec's promises reads zero of them, for every spec we have — so nothing automated can check that list.
  Kind: doc.
  Source: write-spec-doc-lint-2026-08-03.

- 📋 [ONEUP-0076] **Derive a ringless focus cue that measures, in every theme.**
  Split out of ONEUP-0064 on 2026-08-03, after that item's spec converged by cap
  rather than clean at three cold-eyes loops and 762 lines. Across three loops and
  nine lanes essentially every finding fell in this half; the layout half stayed
  quiet. Draft defects fell 24 -> 13 -> 8 while fix collateral rose 0 -> 21 -> 27,
  which is the documented signal that a document is past the review's design
  point. ONEUP-0064 keeps the layout redesign and its own bullet unchanged.

  The measurement that forces the design, reproduced at d18fbf2: a focus cue on
  OneUp's blue buttons CANNOT be built by lightening. Pure white is only 2.63:1
  against the rest fill #4aa3ff, so nothing lighter reaches SC 2.4.13's 3:1 at any
  saturation. The cue must darken. That kills "focus reuses the hover look"
  (CLAUDE.md, the 2026-07-25 decision), because hover lightens -- while leaving
  the no-focus-BORDER constraint untouched, since darkening a fill draws no ring.

  Rather than author a focus colour per theme, the app DERIVES one: the smallest
  blend toward black -- or toward white where black cannot get there -- clearing
  3:1 against every one of the control's rest pixels. Total for a single surface,
  because max(contrast vs black, vs white) never drops below 4.58:1 for any sRGB
  colour. So a palette nobody has written yet still gets a working cue, which is
  what ONEUP-0027's six new themes need, and the same bound gives the label colour
  for free. NOT total for a SET of surfaces -- #000000 and #989898 admit no fill
  at all, and 192 such grey pairs exist -- so the search fails loudly rather than
  returning a colour that does not clear.

  Two other documents are wrong about this and are corrected when this lands:
  ui-and-accessibility.md section 5.4 claims "SC 2.4.7 (Focus Visible) is still
  met" when 16 of the window's 34 focusable widgets have no cue at all, including
  all five toggle switches; and ONEUP-0028 section 5 promises :focus rules for
  eight styled controls when three of them have none, and specifies a 2px accent
  outline the no-focus-ring decision forbids. ONEUP-0028's own section 2 already
  logged that absence as a "WCAG 2.4.7 failure".

  Lands in the same slot ONEUP-0064 occupies in oneup-2.0.md section 5.2: after
  the GUI split (0034), before themes (0027), which inherits the check and owes it
  six passing palettes.

  Test: the ratio computation ships in the suite rather than being asserted --
  every derived pair measured against every rest pixel colour, in every theme,
  with the high-contrast overlay on and off.
  headline_only
  **Layman:** Make it always obvious which control the keyboard is on — without drawing a box round it — and have the app prove it rather than claim it.
  Kind: accessibility.
  Source: split-from-oneup-0064-2026-08-03.

- 📋 [ONEUP-0077] **The window builds the timer notification, instead of asking the engine for it.**
  Split out of ONEUP-0072 on 2026-08-03, on the user's decision. That spec's
  section 11 recommended splitting section 4.4 rather than running a fourth
  cold-eyes loop: it had converged by cap at 654 lines, and every collateral
  critical in its loop 3 landed in section 4.4 or the ordering paragraph beside
  it. ONEUP-0072 keeps the payload conversion -- the three fates, the shape of a
  code, where the wording lives.

  This is a different job that happens to touch the same code. The conversion
  turns engine payloads into codes; this item stops the two headless entry points
  passing --notify and has the window compose the notification itself, from
  @@CHECK@@, @@INSTALLED@@, @@REPO_SKIPPED@@ and @@DONE@@. Three consequences the
  parent spec had already worked out and that come across intact: both paths must
  start passing --log= (they are the only engine runs the window starts without
  one, and the failed-run text names the log file); both must capture the
  engine's output, which today they do not -- they read only its exit status; and
  the firing rules travel with the text, because they are not in the markers.

  ONEUP-0074 folds in here. A run the user stops notifies "Already up to date",
  because the end-of-run fall-through has no stopped branch even though the
  engine emits marker DONE "stopped" twenty lines above it. ONEUP-0072 section
  3.2 forbade itself repairing that -- its gate was that behaviour did not change
  -- but this item is rebuilding the same four-case fall-through in the window,
  so fixing it here costs one branch instead of writing that code twice.

  Needs no application object, which is what made it cheap to land early: nothing
  on either headless path touches Qt. The sentences are ordinary Python tables
  until ONEUP-0032 marks them, and the notification is notify-send. Same slot in
  oneup-2.0.md section 5.2 as ONEUP-0072: after the engine rewrite, before
  translation.

  Test: a scenario asserting a stopped run's notification is not "Already up to
  date" -- today the suite's _notify_case coverage exercises the three reachable
  texts and never the stopped path.
  headline_only
  **Layman:** The weekly background check and update currently let the engine write their desktop notification; the window will write it instead, so there is one place that turns results into sentences.
  Kind: implement.
  Source: split-from-oneup-0072-2026-08-03.

- ✅ [ONEUP-0078] **Bound and show the repository refresh the leftover-packages step triggers.**
  zypper auto-refreshes any stale repository before answering a `packages`
  query, so the orphans step's two `sudo_capture` queries could trigger a
  full metadata fetch. That fetch got neither of ONEUP-0048's defences:
  its output went into a shell variable instead of the log pane, and it
  ran outside refresh_repos' per-source `REFRESH_TIMEOUT` budget — so a
  crawling mirror hangs the run with the window drawing nothing, which is
  the exact failure ONEUP-0048 exists to prevent. Reachable whenever the
  system step is deselected, because nothing has refreshed by then.

  Measured 2026-08-03 on `--steps=flatpak,orphans,cache`: the step took
  1m41s, of which ~81s was one repository (`games`), the whole phase
  silent, and the GUI's 45s stall warning fired on a run that was working.
  Cache timestamps under /var/cache/zypp/{raw,solv} carry the evidence;
  re-run warm, both queries take 1.5s.

  Fix: call refresh_repos (guarded, named, stoppable) before the queries
  when the run has not already refreshed, and pass --no-refresh to both
  so the implicit one cannot happen. Same metadata, same cost, now
  visible and bounded.
  **Layman:** A run with "System packages" switched off could sit silent for minutes on "Removing leftover packages" — it was quietly downloading update lists, with nothing on screen and no time limit.
  Kind: fix.
  Source: user-report-2026-08-03 (screenshot: run appeared hung on step 2 of 3).
  Resolved (2026-08-03): commit ae0b857. refresh_repos runs before the two
  queries when REPOS_REFRESHED is still false, and both carry --no-refresh
  so the implicit fetch cannot happen; a stop between sources now ends the
  step instead of falling through to a removal. Three regression tests in
  tests/run-tests.sh, each verified red against the pre-fix engine. Local
  CI green (210 engine / 283 GUI). Not released — main stays at 1.4.0
  until the user calls a 1.4.1.

- 📋 [ONEUP-0079] **Give the GUI smoke suite a partial tally when it aborts part-way.**
  tests/gui-smoke.py runs its ~300 checks inside one unbroken main(). A real
  exception anywhere aborts every check after it and the run ends on a bare
  traceback instead of the "Passed: N Failed: M" summary at the foot, so the
  output cannot say how many checks never ran. CI still correctly goes red —
  this costs diagnosis, not correctness: a crash near the top and a crash near
  the bottom look identical from the summary.

  Raised INFO by the 2026-08-03 /test-audit sweep, so it is recorded rather
  than fixed. The cheap version is a try/finally around main()'s body printing
  the running tally plus "aborted after N checks" on the way out; the thorough
  version is splitting main() into sections, which is the same change 2.0's
  package split forces anyway (docs/design/oneup-2.0.md).
  **Layman:** If the window's test run crashes half way, the summary at the end can't tell you how many checks never got to run.
  Kind: test.
  Lanes: tests.
  Source: test-audit-2026-08-03.

- ✅ [ONEUP-0080] **Close the 2026-08-03 test-audit findings across all four suites.**
  A /test-audit sweep over the four test programmes, triaged against source.
  Two HIGH, ten MEDIUM and five LOW fixed; one INFO filed as ONEUP-0079; one
  finding dismissed as already-tracked (ONEUP-0062). Five pre-pass pattern hits
  were logged as false positives rather than dropped.

  The two that mattered:

  - tests/docs-check.py ran its disposition pattern over every bold span in a
    loop-log row joined together, so a number ending one span could pair with a
    disposition word starting the next — a bolded timing figure beside a bolded
    "Dismissed" read as 69 outcomes and failed a row that balanced. This is the
    second failure mode recorded on 5df0703, which documented it for authors but
    did not fix the check. Now matched per span.
  - tests/run-tests.sh never mocked `df`, so the engine's pre-flight low-disk
    check read the real machine in every system-step scenario. On a box under
    the 2 GiB threshold that injected a real @@DISK@@|warn line into every one
    of them — the same class as the /run/zypp.pid and run.state defaults that
    §2 of the testing standard exists to prevent. It also unblocks ONEUP-0069.

  Also: bump-test.py asserted only the CHANGELOG and trusted bump.py's exit
  code for the other five sites, which proves its regexes matched but not that
  they wrote the right value — it now reads every site back, against a target
  version no shipped file contains (1.3.0 collided with real history, which
  made two of the read-backs unfalsifiable). Two @@HINT@@ checks named a
  specific hint while asserting only the bare marker. check_eq was defined
  inside one scenario body and used by two others. Four copies of one sudo mock
  became setup_cached_sudo. In the GUI suite: an unrestored dialog stub, a tray
  setting leaked into shared QSettings, a day-count block reading the clock
  twice, a temp-dir block missing the try/finally its sibling has, and a
  teardown check that proved a reference was dropped rather than a timer
  stopped. New GUI coverage for four paths that had none: the download-size
  channel, the CHECK_ITEM package preview, the three snapshot-thinning
  outcomes, and the engine failing to start.

  Verified by re-audit: all fixes held, and the pass caught three vacuous
  assertions among the newly-written GUI checks (a progress-bar range, a status
  string and a button visibility that each matched their constructor default).
  All three were rewritten and then sabotage-tested — removing the production
  line each guards makes exactly those three fail and nothing else.

  Resolved (2026-08-03): local-CI green at 210 / 301 / 12 engine, GUI and bump
  assertions and 14,828 documentation checks. Landed on main under the second
  freeze exception, recorded in docs/standards/workflow.md §1.2; owes a 1.4.x.
  **Layman:** A review of OneUp's own tests found some that could not fail, and some that quietly depended on the machine they ran on. Both are fixed.
  Kind: test.
  Lanes: tests, docs.
  Source: test-audit-2026-08-03.

- ✅ [ONEUP-0081] **Add the GitHub funding file, the only Ants project that lacked one.**
  `.github/FUNDING.yml`, copied byte-identical from the eleven other Ants
  projects that carry one (RetroArch's is upstream libretro's and is not a
  sibling). Repository metadata rather than application code, so the 1.4.0
  freeze in `docs/standards/workflow.md` §1.2 does not reach it — nothing
  in the app, the engine or the packaging changes, and no version site
  moves.
  **Layman:** The repository page now shows a Sponsor button, like every other Ants project does.
  Kind: chore.
  Source: user-request-2026-08-03.
