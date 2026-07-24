%define app_id za.co.antsprojectshub.OneUp

Name:           oneup
Version:        1.2.0
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

The GUI never runs as root; a small engine script (update_system.sh) does the
privileged work behind a single password prompt.

%prep
%autosetup -n oneup-%{version}

%build
# Pure Python — nothing to compile.

%install
# Application payload (GUI + engine live side by side).
install -Dm0644 updater.py        %{buildroot}%{_datadir}/oneup/updater.py
install -Dm0755 update_system.sh  %{buildroot}%{_datadir}/oneup/update_system.sh

# Launcher on PATH. Supports `oneup` (GUI) and `oneup --check` (headless).
install -dm0755 %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/oneup <<'EOF'
#!/bin/sh
exec python3 %{_datadir}/oneup/updater.py "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/oneup

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
%{_datadir}/oneup/
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
%{_datadir}/metainfo/%{app_id}.metainfo.xml

%changelog
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
