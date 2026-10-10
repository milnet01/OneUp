%define app_id za.co.antsprojectshub.OneUp

Name:           oneup
Version:        1.4.7
Release:        0
Summary:        One-click openSUSE update dashboard
License:        MIT
URL:            https://github.com/milnet01/OneUp
Source0:        oneup-%{version}.tar.gz
BuildArch:      noarch

# Installed at build time so the icon's /usr/share/icons/hicolor/... parent dirs
# are owned during the file-list check (also required at runtime, below).
BuildRequires:  hicolor-icon-theme

# The GUI needs Qt for Python; the engine calls zypper. Everything else is
# optional — OneUp skips steps for tools that are not installed.
Requires:       python3-pyside6
Requires:       zypper
# The engine performs every privileged step via sudo; without it the app installs
# but no update can run.
Requires:       sudo
# Owns /usr/share/icons/hicolor/... so the installed SVG's parent dirs are packaged.
Requires:       hicolor-icon-theme
Recommends:     flatpak
Recommends:     fwupd
Recommends:     libnotify-tools
Recommends:     ksshaskpass
Recommends:     snapper

%description
OneUp is a small Qt dashboard that updates openSUSE system packages, Flatpaks
and firmware, and cleans up leftover packages and the download cache — each an
optional toggle. It can check for updates read-only, follow the desktop
light/dark theme, and optionally check weekly in the background and notify you.

The GUI never runs as root; a separate engine (the oneup.engine Python package,
also runnable as oneup-engine) does the privileged work behind a single password
prompt. The previous shell engine, update_system.sh, ships as a fallback.

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

%files
%license LICENSE
%doc README.md
%{_bindir}/oneup
%{_bindir}/oneup-engine
%{_datadir}/oneup/
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
%{_datadir}/metainfo/%{app_id}.metainfo.xml

%changelog
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
