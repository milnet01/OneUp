%define app_id za.co.antsprojectshub.OneUp

Name:           oneup
Version:        2.0.0
Release:        0
Summary:        One-click openSUSE update dashboard
License:        MIT
URL:            https://github.com/milnet01/OneUp
Source0:        oneup-%{version}.tar.gz
BuildArch:      noarch

# Installed at build time so the icon's /usr/share/icons/hicolor/... parent dirs
# are owned during the file-list check (also required at runtime, below).
BuildRequires:  hicolor-icon-theme
# %%{_unitdir} and the %%service_* scriptlets for OneUp's system service.
BuildRequires:  systemd-rpm-macros
%{?systemd_ordering}

# The GUI needs Qt for Python; the engine calls zypper. Everything else is
# optional — OneUp skips steps for tools that are not installed.
Requires:       python3-pyside6
Requires:       zypper
# The engine reaches root through OneUp's system service (ONEUP-0249), which talks
# D-Bus through jeepney. sudo stays: a run from an SSH session falls back to it.
Requires:       python3-jeepney
Requires:       dbus-1
Requires:       sudo
# Owns /usr/share/icons/hicolor/... so the installed SVG's parent dirs are packaged.
Requires:       hicolor-icon-theme
Recommends:     flatpak
Recommends:     fwupd
Recommends:     libnotify-tools
Recommends:     ksshaskpass
Recommends:     snapper
# `zypper ps`, which lists the services to restart after an update, needs lsof (ONEUP-0295).
Recommends:     lsof

%description
OneUp is a small Qt dashboard that updates openSUSE system packages, Flatpaks
and firmware, and cleans up leftover packages and the download cache — each an
optional toggle. It can check for updates read-only, follow the desktop
light/dark theme, and optionally check weekly in the background and notify you.

The GUI never runs as root; a separate engine (the oneup.engine Python package,
also runnable as oneup-engine) decides every privileged step. OneUp's system
service runs those steps as root when this computer's software-update permission
allows it, the same permission Discover uses, so no OneUp password setting is
needed. The previous shell engine, update_system.sh, ships as a fallback.

%prep
%autosetup -n oneup-%{version}

%build
# Pure Python — nothing to compile.

%install
# Application payload (GUI + engine live side by side).
#
# updater.py is a shim over the oneup/ package, so the package must be installed
# beside it and NOT flattened: it is imported as `oneup.gui.app`, which resolves
# relative to the directory updater.py sits in. A directory copy rather than a
# file list, because a module added to the package would otherwise be missing
# from the RPM with nothing failing at build time.
install -Dm0644 updater.py        %{buildroot}%{_datadir}/oneup/updater.py
install -Dm0755 update_system.sh  %{buildroot}%{_datadir}/oneup/update_system.sh
cp -a oneup %{buildroot}%{_datadir}/oneup/oneup
find %{buildroot}%{_datadir}/oneup/oneup -name '__pycache__' -type d -prune -exec rm -rf {} +
find %{buildroot}%{_datadir}/oneup/oneup -type f -exec chmod 0644 {} +
find %{buildroot}%{_datadir}/oneup/oneup -type d -exec chmod 0755 {} +

# Launcher on PATH. Supports `oneup` (GUI) and `oneup --check` (headless).
install -dm0755 %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/oneup <<'EOF'
#!/bin/sh
exec python3 %{_datadir}/oneup/updater.py "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/oneup

# The engine on its own, for a terminal (ONEUP-0054 §4.7). The window does not use
# it: it launches `python3 -m oneup.engine` itself, with the same PYTHONPATH.
cat > %{buildroot}%{_bindir}/oneup-engine <<'EOF'
#!/bin/sh
exec env "PYTHONPATH=%{_datadir}/oneup${PYTHONPATH:+:$PYTHONPATH}" python3 -m oneup.engine "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/oneup-engine

# Desktop entry, icon and AppStream metadata.
install -Dm0644 data/%{app_id}.desktop \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
install -Dm0644 data/%{app_id}.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
install -Dm0644 data/%{app_id}.metainfo.xml \
    %{buildroot}%{_datadir}/metainfo/%{app_id}.metainfo.xml

# OneUp's system service (ONEUP-0249 §4.8): started by D-Bus on demand, never at boot.
# The launcher goes to /usr/libexec on every release, Leap 15 included, where
# %%{_libexecdir} is /usr/lib: the unit's ExecStart names that path.
install -Dm0755 packaging/rpm/oneup-service %{buildroot}/usr/libexec/oneup-service
install -Dm0644 data/oneup-service.service %{buildroot}%{_unitdir}/oneup-service.service
install -Dm0644 data/za.co.antsprojectshub.OneUp1.conf \
    %{buildroot}%{_datadir}/dbus-1/system.d/za.co.antsprojectshub.OneUp1.conf
install -Dm0644 data/za.co.antsprojectshub.OneUp1.service \
    %{buildroot}%{_datadir}/dbus-1/system-services/za.co.antsprojectshub.OneUp1.service

%pre
%service_add_pre oneup-service.service

%post
%service_add_post oneup-service.service

# No %%preun: %%service_del_preun stops the service on removal, and a stop waits for the
# running job. If that job is the zypper removing OneUp, the two wait on each other
# until TimeoutStopSec. Left running, the service exits on its own once idle (§4.8).

%postun
# Never restarted on upgrade: the service may be running the very zypper that is
# upgrading OneUp. The next start after it exits idle loads the new code (§4.8).
%service_del_postun_without_restart oneup-service.service

%files
%license LICENSE
%doc README.md
%{_bindir}/oneup
%{_bindir}/oneup-engine
%{_datadir}/oneup/
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
%{_datadir}/metainfo/%{app_id}.metainfo.xml
%if "%{_libexecdir}" != "/usr/libexec"
%dir /usr/libexec
%endif
/usr/libexec/oneup-service
%{_unitdir}/oneup-service.service
# Co-owned: OBS's filelist check refuses folders no package in the build root owns
# (ONEUP-0379), and the D-Bus packages are not among its build requirements.
%dir %{_datadir}/dbus-1
%dir %{_datadir}/dbus-1/system.d
%dir %{_datadir}/dbus-1/system-services
%{_datadir}/dbus-1/system.d/za.co.antsprojectshub.OneUp1.conf
%{_datadir}/dbus-1/system-services/za.co.antsprojectshub.OneUp1.service

%changelog
* Fri Nov 06 2026 Anthony Schemel <aant.schemel@gmail.com> - 2.0.0-0
- Developers can build the RPM from a commit and look inside it with one command
- Show an estimated time left while packages download.
- Installed from the openSUSE repository or the RPM, OneUp asks for your password the way Discover does
- Clicking a system package shows what it is and, once its new version has downloaded or installed, what changed in it.
- Clicking a Flatpak app shows what it is and which versions are new
- On a screen too small for the window, OneUp scrolls instead of squeezing
- Three window layouts — Rows, Rail and Spotlight — to choose from in Settings, none of which moves or resizes while an update runs
- Each package in the list shows its download size, its source and, during an update, its progress
- OneUp now deletes its own old update logs, after 30 days by default.
- You can stop OneUp asking GitHub for a newer version as it starts
- OneUp is ready to be translated, including into right-to-left languages
- Eight colour themes, chosen in Settings
- After the last package installs, OneUp says it is finishing up instead of looking stuck
- Removing leftover packages shows how far it has got
- The six project standards say they are OneUp's own, so the copied-standards check stops reporting them as copies
- The download size appears by itself where OneUp's system service needs no password
- Show technical log and Open log file are small buttons, not links
- The password box says whose password OneUp needs
- The finished line says how many leftover packages were removed
- Package sizes print with one decimal place for KiB and MiB, as every sketch does.
- The footer is one summary line and a filled red Stop, as in the sketches.
- Spotlight matches the sketch: a large Now panel with three figure boxes, and clean Up next and Done lists.
- Rail matches the sketch: package cards in two columns, a coloured progress strip and a large heading with counts.
- Each step has a short description, and says Waiting until its turn comes
- Rows highlights the package being downloaded now
- Rows' update list shows each package on one line, with where it comes from in a small label
- The chosen package tab is filled in blue, so you can see which list you are looking at
- Rows' package tabs show how many updates each holds
- The progress bars show the running step in two halves: downloading, then installing
- Each package's state is a symbol OneUp draws: a clock, a down arrow, a tick and so on
- Recenter is a small crosshair, and OneUp draws the Settings gear itself
- During an update, Stop stands alone where Run and Check were, as in the layout sketches
- The About window says OneUp is an independent project
- The openSUSE repository has a new address
- Scrollbars now follow the chosen theme
- The weekly timers' notification is written by the app, not the engine
- The engine sends codes, and the window words every message itself (ONEUP-0072, ONEUP-0108)
- OneUp now runs its updates with a new engine written in Python
- The window has been reworked so there is one obvious thing to press.
- You can now see where you are when using the keyboard.
- The app's code is now organised into small, focused files instead of one very large one.
- Switching theme or text size does less work.
- A documented design for 2.0
- Retire the stopfg and stophov palette keys, which no stylesheet uses since Stop is filled.
- Every failed step now says something
- Rail keeps its words at Larger
- Closer to the approved pictures
- Spotlight keeps whole sizes
- Counts read as English
- Text size now reaches every button
- Spotlight shows the whole last-run line
- Check counts every package the update will change
- The Flatpak step says which pass it is on and how far through it is
- The window's package counts and sizes agree with zypper during a parallel download
- When the password box cannot start, OneUp says so and names the command
- A system update that fails part-way ends the run, and says so
- After a half-finished system update, OneUp says the system is partly updated
- An rpm install failure is no longer called a package conflict
- No "approve the password popup" when no popup is coming
- A package's details open even when its text is not plain UTF-8
- The outline around "Retry failed steps" is easier to see on the amber warning strip
- The lists of updates now grow with Text size, like the rest of the window
- No blue box round a button's label when it is reached with the Tab key
- The words stay on "Installing" once the bar is in its install half
- Spotlight's and Rail's step names are shown whole
- Spotlight's Packages box counts up when the total is not known
- Settings, Recenter and About are the same height
- Spotlight's package lists no longer scroll sideways
- The package list always shows a few packages, even in the smallest window
- In the Rail layout the step names are no longer cut short
- The finished line says what was installed from each source
- Check for updates works straight after the download size is shown
- The progress bar's fill is easy to see in the four light themes
- The Stop button no longer shrinks when it replaces Check for updates.
- The key-import dialog and the package-conflict hint say "source", like the rest of the window
- Engine tidy-ups: exact log path, a hold that ends on time after sleep, and no lost repository after an interrupted cleanup
- A warning's button always matches the warning above it
- Thinning old snapshots now tells you how it went
- Offline, the firmware step no longer says "up to date" from an old firmware list
- The signing-key messages say "source", like the rest of the window
- The window opens where you last left it, including after a restart, on KDE Wayland
- Pressing Update after "Show download size" carries on from the size check instead of asking for your password again
- A weekly update you stopped no longer says "Already up to date"
- Two test runs at once no longer fail each other
- The window can no longer stop following a run because of one odd character
- The two engines no longer disagree about where a line ends or what a counter looks like
- The check that keeps the engine and its contract in step now covers the Python engine
- A rejected request to start the update is now reported, not shown as success
- A full disk no longer produces an endless stream of error boxes
- The update engine copes with a full disk, an odd character and a close-run timer
- A bad keep-alive interval no longer makes the engine spin
- The words on the progress bar were too faint to read against the coloured fill
- Asking for the download size with no step name started a full update
- A stalled software source can no longer hang a run with nothing on screen
- The "still working" line now appears while checking for updates, not only while installing
- Screen readers now speak the actual message instead of a fixed word
- The progress caption is readable in high contrast, and faint borders were darkened
- Stopping during a retry is no longer reported as a completed update
- Steps no longer say "up to date" when they could not check
- The computer can no longer be shut down mid-update on the usual update path
- Changing the colour theme no longer starts an update
- Text and controls that were too faint to read reliably
- One password box instead of two when you check the download size first.
- OneUp now respects XDG_STATE_HOME, the standard setting for where apps keep their working files.
- The AppImage build installs exact versions of PySide6 and PyInstaller.
- Passwordless setup names the real account
- Package names from the system are checked before reaching a privileged removal
- The downloadable AppImage is now built from exactly pinned tooling
* Thu Nov 05 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.12-0
- Updating over SSH with no desktop asks for the password in the terminal
- The "Last run" date uses your language's name for the month
- The progress bar's fill is easy to see in the light theme
* Sun Nov 01 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.11-0
- Pressing Stop during a retried download no longer says the system was updated
- OneUp says when it could not list leftover packages
- No garbled characters in OneUp's messages
- A read error no longer stops a running update
- Updating only some things no longer makes the tray say "up to date"
- Reopening OneUp during an update no longer misreads its progress
- Less work on each download-size check
- When the password box cannot start, OneUp says so and names the command
- A system update that fails part-way ends the run, and says so
- An rpm install failure is no longer called a package conflict
- No "approve the password popup" when Passwordless is on
- The log says when the list of services to restart could not be checked
- No blue box round a button's label when it is reached with the Tab key
- The count of installed updates includes new packages
- The progress line stops naming a repository once packages download
* Wed Oct 14 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.10-0
- The openSUSE repository has a new address
- Stopping during the download is reported as a stop, not a failure
- The signing-key hint appears only for a real signing-key problem
- The download figure reaches the end when some packages were already downloaded
- A run that updated only Flatpak apps no longer says nothing was needed
* Tue Oct 13 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.9-0
- The GitHub release page lists what changed again
- A stuck release build now fails within 30 minutes
* Tue Oct 13 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.8-0
- Outlined buttons are easy to read in the light theme
- Blue links are easy to read in the light theme
- The "Show download size" link is readable again on the opened System row
- A run no longer offers a restore point that does not exist, and the terminal help lists --size
- Five small window fixes: safer restart questions, honest results, no stuck buttons
- A warning's button always matches the warning above it
- Offline, the firmware step no longer says "up to date" from an old firmware list
- Three buttons showed a stray underline where an "&" belongs
- Small messages now open over the OneUp window, not in the corner of the screen
- A window you moved stays where you put it when a message appears
- The window no longer stutters during a big download
* Sat Oct 10 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.7-0
- The release build finishes again, so this version gets a GitHub release page and an AppImage
* Thu Oct 08 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.6-0
- The words on the progress bar are readable again where the bar is filled.
- The Stop button greys out while packages install
- An update that first updated zypper itself now finishes the rest
- An update that stops on a package conflict now says so
- OneUp no longer claims it kept downloaded packages when nothing was downloaded
- "Restart services" now tells you whether it worked
- The window no longer blames the server when an update is just busy writing to a slow disk
- A run started from a terminal no longer asks for the password again, unseen, after five minutes
- A full or read-only disk, or a damaged settings value, no longer breaks OneUp's window
- A tall window, such as the software sources manager, no longer opens with its top off the screen on X11
- Turning on automatic updates right after opening OneUp no longer switches itself back off
- "Copy diagnostics" no longer mangles the report on a computer with a short name
- Updating the OneUp AppImage no longer silently stops the weekly check, automatic updates or start-at-boot
- Removing leftover packages no longer fails on a package called "Name"
- The Flatpak step no longer says "up to date" right after updating an app
- "Show download size" no longer says "nothing to fetch" when part of the update is already downloaded
- Firmware is no longer reported as up to date when OneUp couldn't ask
- A safety snapshot that failed is no longer offered as this update's restore point
- Tidying old snapshots no longer says there was nothing to tidy when it failed
- Sizes use the right unit names, and an unknown result no longer shows as Done
- The Repositories and Roll back windows say what actually changed
- Starting a second update no longer breaks the Stop button of the first
- The window can no longer catch the run record half-written
- Software-source names are checked before any root command sees them
* Wed Aug 19 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.5-0
- Offers the restart instead of telling you one is needed
* Tue Aug 18 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.4-0
- Restart services never restarts something that would log you out
- Restart services now actually restarts them
* Wed Aug 12 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.3-0
- Automatic weekly updates switch themselves off if Passwordless stops working.
- Turning on Passwordless now really does stop the password box.
* Fri Aug 07 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.2-0
- An update no longer fails because one package refused to download.
* Fri Aug 07 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.1-0
- Window-side test coverage for four paths that had none.
- The update check says what actually went wrong.
- High-contrast mode is readable again in Settings and Repositories.
- Only one copy of OneUp can run at a time.
- A failed update no longer throws away everything it downloaded.
- Rebooting during an update no longer hangs on a black screen.
- Stop now works while packages are downloading.
- Three ways the window's test run could leak state into later checks.
- The version-bump test now proves all six version sites, not just the changelog.
- The engine test suite no longer reads the real machine's free disk space.
- The documentation loop-log tally check no longer fails a correctly-formed row.
- Stop the leftover-packages step going silent for minutes on a slow mirror.
* Sun Jul 26 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.4.0-0
- Warn when zypper's wording changes instead of silently showing no progress.
- Add a Stop button that never interrupts an install half-way.
- Pick up and follow a run that is already in progress when the window opens.
- Stop the test suite reading, and damaging, real machine state.
- Never report "up to date" for a source the check couldn't read.
- The GUI test suite no longer reads the machine's real zypper package cache
- Open dialogs over the app window on Wayland, where move() is ignored.
- Make a slow mirror legible instead of indistinguishable from a hang.
* Sat Jul 25 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.3.0-0
- Show live per-package progress so a long download can't look like a hang.
- Accessibility: screen-reader support, larger text, and a high-contrast option
- Roll back to a chosen restore point, not just the last one
- A pre-update warning when Btrfs snapshots pile up, with a one-click "Thin snapshots" button.
- "Show download size" now says how long the wait will be
- Close an orphaned password dialog instead of leaving it on screen.
- Never abandon an update half-way when the app is closed.
- Stop the sudo keep-alive outliving a killed run.
- Name the program holding the package lock instead of failing every step through it.
- Ask for the password once per run, not once per privileged step.
- the download-size check asked for a password twice
- steps launched from the window could fail with "a terminal is required"
- "Show download size" reported 0 B for every update
- The signing-key-import and passwordless-consent popups now open centered over the main window, matching the About and Repositories dialogs.
- bump.py: advance the CHANGELOG [Unreleased] compare-link base to the new tag.
* Fri Jul 24 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.2.0-0
- Add a one-click 'copy diagnostics for a bug report' button.
- Report how much disk the cache clean reclaimed
- OneUp now survives a single broken software source instead of failing the whole update.
- An optional system-tray icon that turns amber when updates are waiting.
- An optional "Automatic updates" setting that installs everything on a weekly schedule — off by default.
- An opt-in "Passwordless" setting so OneUp stops asking for your password on every update.
- You can now preview exactly what an update will change before running it.
- When a repository's signing key is out of date, OneUp can now fix it for you — with a "Import signing key & retry" button, behind a clear confirmation.
- When a step suggests a command OneUp couldn't run for you, the warning banner now has a "Copy command" button
- Show a 'last updated N days ago' nudge on launch.
- Cap or roll the tray-check log files so a long resident session doesn't accumulate them.
- Call out kernel and graphics-driver updates by name in the reboot advice.
* Tue Jul 21 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.1.0-0
- Each repository in the Repositories manager now shows a plain-English line describing what it's for.
- A Repositories manager (from the header) to turn software repositories on/off with switches and remove ones that duplicate another repo's URL — the duplicate-repo warning now opens it.
- Each task row now shows how long the step took next to what it did — e.g. "3 installed · 42s".
- An "About" window (from the header) showing the version, MIT licence, GitHub and openSUSE package links, and a manual "check for updates" button that reports the result either way.
- A desktop notification when an update you started finishes — so a run you walked away from still tells you it's done (only pops up when the window isn't focused).
- The current version is shown in the window title and header.
- Flatpak reports how many apps it updated (counted before the update, like the check does).
- Each task row now shows what happened after a real update — e.g. "3 installed", "Up to date", "Updated", "Failed" — not just after a check.
- The Repositories manager is wider so repo URLs aren't clipped and remembers its size; the About and Repositories popups now open centered over the main window.
- The duplicate-repository warning now names the offending URL and tells you how to remove it, instead of a generic "duplicates detected" message.
- The update engine now runs under bash strict mode (set -uo pipefail) so unset variables and mid-pipeline failures surface immediately instead of silently.
- A failed repository refresh no longer marks a successful system upgrade as failed.
- The sudo keep-alive no longer leaves a short-lived background process behind when a run ends or is cancelled.
* Tue Jul 21 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.0.1-0
- Audit + independent-review fixes: firmware no longer reports success/forces a
  reboot on a failed flash; Ctrl-C aborts a run; locale-robust update detection;
  rollback and service-restart input validation; and packaging/dependency fixes.
* Tue Jul 21 2026 Anthony Schemel <aant.schemel@gmail.com> - 1.0.0-0
- First release.
