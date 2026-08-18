# Changelog

All notable changes to OneUp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and OneUp uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **Restart services never restarts something that would log you out** (ONEUP-0111)
  After a big update the list of services to restart can include the ones running
  your desktop — the display manager, your own session, the system message bus.
  Restarting those would have ended your session and closed OneUp part-way
  through. The window now restarts only what is safe and tells you plainly that
  the rest need a reboot, and the banner stays up while any of them are
  outstanding. Running the update script in a terminal gives the same warning.

- **Restart services now actually restarts them** (ONEUP-0110)
  The button did nothing at all when clicked. The window validates each service
  name before handing it to a root systemctl, and that check required a
  ".service" suffix — but `zypper ps -sss` reports bare unit names, so every
  name was rejected and the handler gave up silently. The check now accepts a
  bare name and still refuses anything that could be read as a command-line
  option.

## [1.4.3] - 2026-08-12

### Fixed

- **Automatic weekly updates switch themselves off if Passwordless stops working.** (ONEUP-0099)
  Automatic updates need the Passwordless setting to run unattended, and
  OneUp already turned them off when you switched that setting off
  yourself. It did not notice the other ways the permission can go away —
  removed outside OneUp, or left behind by an older version. The weekly
  update then kept firing into a password box nobody was looking at and
  installed nothing, every week, silently. Now OneUp stands the schedule
  down as soon as it notices, and tells you why.

- **Turning on Passwordless now really does stop the password box.** (ONEUP-0092)
  The setting told the system to trust five of OneUp's commands, but an
  update runs three more it had never been told about — checking each
  software source, downloading the packages, and measuring the cleanup. So
  the password box still appeared, usually at "Checking for updates from…"
  right at the start. All three are covered now, and OneUp decides whether
  the setting is working by checking what a real update actually does,
  rather than asking about one command out of six. If the permission was
  set up by an older OneUp, the app notices and asks you once, up front,
  instead of surprising you in the middle of a run. Firmware is the one
  exception: it asks the system for permission its own way, and no setting
  of OneUp's can speak for it.

## [1.4.2] - 2026-08-07

### Fixed

- **An update no longer fails because one package refused to download.** (ONEUP-0094)
  openSUSE spreads its packages across mirrors, and for a brand-new update
  it can send one file to a server that is too slow to finish sending it.
  When that happened the whole update was thrown away — 82 packages
  downloaded, one that would not arrive, and nothing installed. OneUp now
  notices that kind of failure and quietly fetches the packages again from
  openSUSE's content delivery network, which always has them, and the
  update finishes. If that does not work either, it names the package that
  would not come down instead of telling you to check an internet
  connection that is fine.

## [1.4.1] - 2026-08-07

### Added

- **Window-side test coverage for four paths that had none.**
  The download-size channel, the per-package changed-package preview, the three outcomes of thinning old snapshots, and the engine failing to start. The size checks pin the rule that a failed probe must never report "nothing to download".

### Fixed

- **The update check says what actually went wrong.**
  "Couldn't reach GitHub" was shown for every failure, including ones
  where GitHub answered perfectly well to say the hourly check limit was
  used up — sending people to check their internet over something that
  fixes itself on the hour. (ONEUP-0089)

- **High-contrast mode is readable again in Settings and Repositories.**
  Turning on high contrast made the rows in both windows solid white with
  near-invisible text — the exact combination high contrast exists to
  prevent. (ONEUP-0088)

- **Only one copy of OneUp can run at a time.**
  Two tray icons could appear after logging out and back in, because the
  guard against a second copy was only active when the tray setting was
  on — and it deleted its own lock on startup, so two copies launched
  together both survived. Two copies mean two background checks and two
  updates able to collide. (ONEUP-0084)

- **A failed update no longer throws away everything it downloaded.**
  When the system step failed, the cache-cleaning step still ran and
  deleted the packages that had downloaded successfully, so retrying
  started again from zero over the same connection that had just failed.
  Measured on a real run: 424 MB discarded after a download failure. The
  cache is now kept when the update failed, and still cleared when it
  succeeded. (ONEUP-0087)

- **Rebooting during an update no longer hangs on a black screen.**
  A reboot or logout asked for mid-update waited on a process the desktop
  had no permission to stop, long after the screen had been torn down —
  leaving a hard power-off as the only way out, at the worst possible
  moment. OneUp now holds a shutdown lock for the length of a run, so the
  desktop tells you an update is in progress and lets you decide.
  (ONEUP-0086)

- **Stop now works while packages are downloading.**
  Pressing Stop during a download did nothing until the whole step
  finished, which on a stalled mirror meant never — while the screen said
  "Stopping now is safe". The update is now fetched in one pass and
  installed in another, so a stop lands during the download, within
  seconds, with nothing installed and every downloaded package kept.
  Installing itself is still never interrupted, because cutting an install
  half-way can leave programs broken. (ONEUP-0085)

- **Three ways the window's test run could leak state into later checks.**
  A dialog stub was left installed for the rest of the run, a tray setting was persisted to shared storage and never reset, and the day-count checks read the clock twice so a run straddling midnight could shift every count by one.

- **The version-bump test now proves all six version sites, not just the changelog.**
  It asserted only the CHANGELOG rewrite and otherwise trusted bump.py's exit code, which proves its patterns matched but not that they wrote the right value. Every site is now read back and checked at its own pattern, against a target version no shipped file already contains.

- **The engine test suite no longer reads the real machine's free disk space.**
  The pre-flight low-disk check calls `df`, which `setup_common` did not mock, so on a machine under the 2 GiB threshold every system-step scenario picked up a real low-disk warning sourced from the developer's own disk. `df` is now mocked like every other system tool.

- **The documentation loop-log tally check no longer fails a correctly-formed row.**
  It ran its disposition pattern over every bold span joined together, so a number ending one span could pair with a disposition word starting the next — a bolded timing figure beside a bolded "Dismissed" read as a count of 69 and failed a row that balanced perfectly. Each span is now matched on its own.

- **Stop the leftover-packages step going silent for minutes on a slow mirror.** (ONEUP-0078)
  With "System packages" switched off, this step quietly downloaded update
  lists before it could answer — showing nothing on screen and with no time
  limit, so a slow server looked exactly like a frozen app. It now names the
  source it is fetching, gives up on one that is too slow, and can be stopped.

## [1.4.0] - 2026-07-26

### Added

- **Warn when zypper's wording changes instead of silently showing no progress.** (ONEUP-0046)
  If a future zypper renames its output, OneUp says so rather than quietly showing no progress.

- **Add a Stop button that never interrupts an install half-way.** (ONEUP-0047)
  You can now stop an update. It finishes the step it is on first, so nothing is left half-installed.

- **Pick up and follow a run that is already in progress when the window opens.** (ONEUP-0045)
  If an update is already running when you open OneUp, it now shows you that run's live progress instead of looking idle.

### Changed

- **Stop the test suite reading, and damaging, real machine state.** (ONEUP-0050)
  The tests no longer depend on what the computer happens to be doing, and can no longer disturb a real update that is running.

### Fixed

- **Never report "up to date" for a source the check couldn't read.** (ONEUP-0056)
  OneUp said "Everything is up to date" while 8 updates were waiting — it now says when it couldn't check something instead of guessing.

- **The GUI test suite no longer reads the machine's real zypper package cache** (ONEUP-0055)
  A liveness-line test weighed /var/cache/zypp/packages instead of a
  directory of its own, so its verdict depended on what a real update
  had left behind — it passed, then failed on identical code once 44 MB
  of packages were sitting there. Same class as ONEUP-0045/0050, which
  fixed the engine suite; the GUI suite had one left.

- **Open dialogs over the app window on Wayland, where move() is ignored.** (ONEUP-0049)
  Settings, Repositories and the message boxes now appear in the middle of the OneUp window instead of wherever the desktop felt like putting them.

- **Make a slow mirror legible instead of indistinguishable from a hang.** (ONEUP-0048)
  OneUp now shows which source it is fetching, the download size and speed, and how long it has been waiting — and gives up on a source that is too slow rather than waiting hours.

## [1.3.0] - 2026-07-25

### Added

- **Show live per-package progress so a long download can't look like a hang.** (ONEUP-0040)
  While OneUp downloads and installs, it now says "Downloading 12 of 141 packages" instead of sitting on one line for minutes.

- **Accessibility: screen-reader support, larger text, and a high-contrast option** (ONEUP-0028)
  Every control now has a spoken name and the task switches report
  their on/off state, so nothing announces as an unlabelled button.
  Progress, each step's outcome and the final summary are spoken.
  Settings gains Text size (Normal/Large/Larger) on top of your
  desktop's own font size, and a High contrast option. No state is
  signalled by colour alone any more: the switches show a bar for on
  and a circle for off, the tray icon draws a "!" when updates are
  waiting, and an overdue last run says so in words.

- **Roll back to a chosen restore point, not just the last one** (ONEUP-0020)
  The "Roll back this update" action now opens a picker listing recent Snapper
  snapshots with their dates and descriptions, so you can undo a problem that
  started an update or two ago — not only the most recent run. The point taken
  just before the update is pre-selected.

- **A pre-update warning when Btrfs snapshots pile up, with a one-click "Thin snapshots" button.** (ONEUP-0021)
  On Tumbleweed a snapshot pair is taken around every zypper transaction, so restore points quietly accumulate and can fill the root filesystem. OneUp's pre-flight now counts them and, once a lot have built up, shows a dismissible heads-up plus a "Thin snapshots…" button. Thinning runs snapper's own retention cleanup (`number`/`timeline`), which only drops snapshots the configured policy already considers expendable — the most recent rollback points are always kept — and reports how many were removed.

### Changed

- **"Show download size" now says how long the wait will be**
  Working out the figure means asking zypper to plan the whole upgrade,
  which takes tens of seconds on a big Tumbleweed update. The button now
  reads "Calculating… (up to a minute)" instead of a bare "Calculating…",
  and screen-reader users hear the same expectation, so a normal wait
  doesn't look like a stuck button.

### Fixed

- **Close an orphaned password dialog instead of leaving it on screen.** (ONEUP-0043)
  OneUp no longer leaves stray password boxes sitting on your desktop after a run.

- **Never abandon an update half-way when the app is closed.** (ONEUP-0042)
  Closing OneUp during an update now warns you first, and the update itself finishes safely in the background instead of being cut off.

- **Stop the sudo keep-alive outliving a killed run.** (ONEUP-0041)
  An interrupted update no longer leaves a background helper running for hours.

- **Name the program holding the package lock instead of failing every step through it.** (ONEUP-0039)
  If something else is already installing software, OneUp now says so in one clear sentence and changes nothing, instead of reporting a pile of failures.

- **Ask for the password once per run, not once per privileged step.** (ONEUP-0038)
  OneUp now asks for your password a single time per update run instead of popping the box three or more times.

- **the download-size check asked for a password twice** (ONEUP-0037)
  The second prompt was sudo's own unlabelled "password for root" box.
  It now asks once, and any prompt OneUp causes says that OneUp is
  asking and why.

- **steps launched from the window could fail with "a terminal is required"** (ONEUP-0036)
  The password helper was not exported to the engine's privileged
  commands, so a step that needed a password but couldn't see the
  up-front one — "Show download size" was the visible case — failed
  outright instead of showing the KDE password popup.

- **"Show download size" reported 0 B for every update** (ONEUP-0035)
  Current zypper renamed its summary line to "Package download size",
  so the old parse matched nothing and a 371.4 MiB upgrade was shown as
  "0 B to download". Both wordings are now accepted. A dry run that
  actually fails (cancelled password prompt, busy package manager) no
  longer reports a confident 0 B either — it says why and lets you retry.

- **The signing-key-import and passwordless-consent popups now open centered over the main window, matching the About and Repositories dialogs.** (ONEUP-0026)

- **bump.py: advance the CHANGELOG [Unreleased] compare-link base to the new tag.** (ONEUP-0033)
  When cutting a release, the changelog's "Unreleased" comparison link kept pointing at the previous version instead of the one just released, so it showed the wrong range. The release tool now updates it automatically — and also leaves a fresh empty "Unreleased" heading for the next cycle instead of removing it — with a new `tests/bump-test.py` guarding both.

## [1.2.0] - 2026-07-24

### Added

- **Add a one-click 'copy diagnostics for a bug report' button.** (ONEUP-0031)
  One button that copies the run log plus version info to the clipboard, so filing a bug report doesn't mean hunting through hidden folders.

- **Report how much disk the cache clean reclaimed** (ONEUP-0029)
  The cache step now measures /var/cache/zypp before and after `zypper clean --all` and shows the space it freed (e.g. "Reclaimed 1.4G") on the cache row, so the one task with no visible payoff finally has one. Nothing is shown when the cache was already empty.

- **OneUp now survives a single broken software source instead of failing the whole update.**
  When one repository serves a bad signature or is unreachable, OneUp sets just that source
  aside, updates everything else, and retries it next time. A manual run offers "Skip
  &lt;source&gt; & update the rest"; an unattended run skips it automatically and tells you.
  It never weakens the signature check — the source is only set aside, never forced.

- **An optional system-tray icon that turns amber when updates are waiting.**
  Off by default. When on, OneUp keeps running quietly in the tray; the icon goes
  amber whenever a background check finds updates, and a right-click menu gives
  Check now / Update now / Open OneUp / Quit. An optional "Start at boot" launches
  it hidden at login. It checks every few hours using the same read-only,
  password-free check as the weekly popup — so it stays quiet, replacing the popup
  with an at-a-glance icon — and degrades cleanly on desktops without a system tray.

- **An optional "Automatic updates" setting that installs everything on a weekly schedule — off by default.**
  When turned on, OneUp runs the full update once a week in the background, with
  the same pre-update snapshot and one-click rollback a manual run gets. Because
  an unattended run can't stop to ask for a password, it needs the "Passwordless"
  setting: turning Automatic updates on offers to switch both on together, and
  turning Passwordless off switches Automatic updates off too — so you're never
  left with a schedule that would silently fail. The three background settings
  (weekly check, passwordless, automatic updates) now live behind a single
  **⚙ Settings** button in the header.

- **An opt-in "Passwordless" setting so OneUp stops asking for your password on every update.**
  It stores no password — the operating system remembers the *decision* (a
  scoped, revocable rule covering only OneUp's update commands), not the
  password. It's off by default; turning it on asks for your password once to
  set it up, and turning it off removes the rule instantly. OneUp shows a clear
  warning first, because letting updates run without a password is effectively
  passwordless administrator access on that machine.

- **You can now preview exactly what an update will change before running it.**
  The read-only "Check" lists the packages that will change (name, old → new
  version) in an expandable panel on each task, and the system task gains a
  "Show download size" link that fetches the total download size on demand.
  The instant check stays password-free; only the size link asks for
  authentication.

- **When a repository's signing key is out of date, OneUp can now fix it for you — with a "Import signing key & retry" button, behind a clear confirmation.**
  When the system upgrade is refused because a repository's signing key has
  changed or expired, the warning now offers a one-click fix: OneUp imports the
  repository's new key and re-runs the update. Because importing a key is a
  trust decision, it first shows a plain-English confirmation explaining what's
  happening and warning you to only do it for repositories you set up and trust.
  A normal run never imports keys on its own — the fix only happens when you
  approve it.

- **When a step suggests a command OneUp couldn't run for you, the warning banner now has a "Copy command" button** so you can grab the exact command instead of retyping it.

### Changed

- **Show a 'last updated N days ago' nudge on launch.** (ONEUP-0030)
  On opening OneUp, remind the user how long since their last update, and gently flag it once it's been a couple of weeks.

- **Cap or roll the tray-check log files so a long resident session doesn't accumulate them.** (ONEUP-0024)
  When the tray runs for weeks, each background check leaves a small log file; reuse one rolling log instead of piling up new ones.

- **Call out kernel and graphics-driver updates by name in the reboot advice.** (ONEUP-0019)
  When a reboot is advised, say why in plain English - e.g. a new kernel and your NVIDIA driver were installed - instead of a generic 'reboot advised'.

## [1.1.0] - 2026-07-21

### Added

- **Each repository in the Repositories manager now shows a plain-English line describing what it's for.**

- **A Repositories manager (from the header) to turn software repositories on/off with switches and remove ones that duplicate another repo's URL — the duplicate-repo warning now opens it.**
  Listing is read-only (no admin rights); flipping switches or removing a
  duplicate is applied together with a single administrator prompt. Repo
  names are validated before they reach the privileged command.

- **Each task row now shows how long the step took next to what it did — e.g. "3 installed · 42s".**

- **An "About" window (from the header) showing the version, MIT licence, GitHub and openSUSE package links, and a manual "check for updates" button that reports the result either way.**

- **A desktop notification when an update you started finishes — so a run you walked away from still tells you it's done (only pops up when the window isn't focused).**

- **The current version is shown in the window title and header.**

- **Flatpak reports how many apps it updated (counted before the update, like the check does).**

- **Each task row now shows what happened after a real update — e.g. "3 installed", "Up to date", "Updated", "Failed" — not just after a check.**

### Changed

- **The Repositories manager is wider so repo URLs aren't clipped and remembers its size; the About and Repositories popups now open centered over the main window.**

- **The duplicate-repository warning now names the offending URL and tells you how to remove it, instead of a generic "duplicates detected" message.**

- **The update engine now runs under bash strict mode (set -uo pipefail) so unset variables and mid-pipeline failures surface immediately instead of silently.**

### Fixed

- **A failed repository refresh no longer marks a successful system upgrade as failed.**
  The system step's success now follows the upgrade transaction itself,
  not the preceding repo refresh — so an upgrade that installs packages
  from cached metadata is reported as done (with reboot/rollback advice),
  and a refresh that couldn't reach a mirror is surfaced as a note rather
  than a false failure.

- **The sudo keep-alive no longer leaves a short-lived background process behind when a run ends or is cancelled.**
  The keep-alive loop now runs in its own process group and is torn
  down as a group, so its idle `sleep` can't be orphaned (reparented to
  init for up to ~50s) after the run finishes.

## [1.0.1] - 2026-07-21

### Added

- **Added a dependency policy standard with a known-incompatibility ledger (docs/standards/dependencies.md).**

### Changed

- **RPM now requires sudo (the engine can't run any step without it); the launcher uses the packaged data path.**

- **RPM recommends snapper (the rollback feature depends on it); desktop and AppStream categories aligned.**

- **CI actions bumped to latest (checkout v7, setup-python v7, action-gh-release v3); Python build pinned to 3.13.**

### Fixed

- **"Restart services" now validates unit names before running them as root.**
  Service names come from the engine's output stream; only well-formed unit names are passed to the root systemctl, mirroring the rollback snapshot-id guard.

- **Corrected the OBS packaging guide to the home:milnet project (was home:milnet01).**

- **The weekly-check unit now also escapes $, backslash and quotes in the executable path (not just %).**

- **The sudo keep-alive survives a transient authentication blip instead of stopping for the rest of the run.**

- **Rollback validates the snapshot id before running it as root.**
  The snapshot number is checked to be numeric before it reaches the pkexec command, so a malformed value on the output stream can't be interpolated into a root shell command.

- **Ctrl-C (or SIGTERM) now cancels a run instead of cleaning up and continuing through the remaining steps.**
  The interrupt/terminate traps now exit the script, so an aborted run no longer plows on through flatpak/firmware/orphan-removal/cache after you cancel.

- **The self-update check tolerates a non-object JSON reply without throwing.**

- **The weekly-check systemd unit escapes '%' in the executable path so a '%' in the install path can't silently break the timer.**

- **An empty or unknown --steps value is rejected instead of reporting a clean run that did nothing.**

- **The sudo keep-alive is cleaned up on Ctrl-C / SIGTERM, not just normal exit.**
  trap now covers INT/TERM/HUP so an interrupted run can't leak a background loop that keeps root credentials warm.

- **Up-to-date detection is reliable on non-English systems (zypper output pinned to LC_ALL=C).**

- **Low-disk and duplicate-repo pre-flight warnings now surface in the GUI.**
  The engine emitted @@DISK@@/@@REPO@@ markers that the GUI had no handler for, so the advertised warning never appeared; both are now shown live.

- **Malformed progress markers can no longer throw out of the GUI's read slot.**
  A STEP_BEGIN line spliced by interleaved output raised an unhandled IndexError/ValueError that dropped the run's later markers; the field parse is now guarded.

- **Firmware step no longer reports success or forces a reboot when the flash actually failed.**
  fwupdmgr update failures were masked by `|| true` and always recorded as "updates applied" with a reboot nag; the step now gates success and the reboot advice on the real exit code.

## [1.0.0] - 2026-07-21

First public release — one-click updates for openSUSE system packages, Flatpaks
and firmware, plus leftover-package and cache cleanup.

### Added
- **Check for updates** — a read-only pass that reports how many updates are
  available per task (system / Flatpak / firmware) without installing anything.
- **Weekly background check** — an optional toggle that installs a systemd-user
  timer and raises a desktop notification when updates are ready.
- **Light/dark theme** — the window now follows the desktop colour scheme and
  switches live.
- **Restart services instead of rebooting** — after a package-only update, OneUp
  offers to restart just the affected services rather than the whole machine.
- **Retry failed steps** — re-run only the steps that errored.
- **Open log file** — jump straight to the saved log of the last run.
- **Roll back this update** — restore the pre-update snapshot (and reboot) from
  a labelled `OneUp pre-update <date>` snapper snapshot.
- **Pre-flight checks** — warn about low disk space (`/`, `/var`) and duplicate
  repository URLs before starting.
- **Plain-English error hints** — common zypper failures (disk full, bad GPG
  key, network, package conflict) are explained in one line.
- **Self-update check** — notice when a newer OneUp release is available.
- **Single-file AppImage** and an **RPM** package; a release workflow builds and
  attaches the AppImage to each tagged GitHub release.

### Fixed
- No longer advises a reboot when nothing was installed, or when a step failed
  (the false-"reboot needed" nag).
- Stops PackageKit holding the package lock before running zypper, so updates
  don't fail right after login.
- Cache clean-up runs non-interactively (no more "bad stream or EOF").

[Unreleased]: https://github.com/milnet01/OneUp/compare/v1.4.3...HEAD
[1.4.3]: https://github.com/milnet01/OneUp/releases/tag/v1.4.3
[1.4.2]: https://github.com/milnet01/OneUp/releases/tag/v1.4.2
[1.4.1]: https://github.com/milnet01/OneUp/releases/tag/v1.4.1
[1.4.0]: https://github.com/milnet01/OneUp/releases/tag/v1.4.0
[1.3.0]: https://github.com/milnet01/OneUp/releases/tag/v1.3.0
[1.2.0]: https://github.com/milnet01/OneUp/releases/tag/v1.2.0
[1.1.0]: https://github.com/milnet01/OneUp/releases/tag/v1.1.0
[1.0.1]: https://github.com/milnet01/OneUp/releases/tag/v1.0.1
[1.0.0]: https://github.com/milnet01/OneUp/releases/tag/v1.0.0
